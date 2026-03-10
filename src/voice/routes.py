"""Voice API routes for phone call negotiations."""
import json
from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .twilio_client import get_twilio_client
from .call_manager import get_call_manager, CallStatus
from .voice_negotiator import create_greeting, process_human_response, create_closing
from .speech import transcribe_audio, generate_speech, base64_to_audio, audio_to_base64
from ..auth.dependencies import require_auth
from ..repositories import CompanyRepo
from ..config import logger

router = APIRouter(prefix="/api/voice", tags=["Voice"])


class InitiateCallRequest(BaseModel):
    """Request to initiate a phone call."""
    provider_id: str
    session_id: str | None = None
    item_description: str = Field(..., min_length=5)
    target_price: float = Field(..., gt=0)
    max_price: float = Field(..., gt=0)


class CallResponse(BaseModel):
    """Response with call details."""
    call_id: str
    status: str
    provider_name: str
    phone_number: str


@router.get("/status")
async def voice_status():
    """Check if voice calling is available."""
    client = get_twilio_client()
    return {
        "available": client.is_configured,
        "message": "Voice calling is ready" if client.is_configured else "Twilio not configured",
    }


@router.post("/call", response_model=CallResponse)
async def initiate_call(
    request: InitiateCallRequest,
    user: Annotated[dict, Depends(require_auth)],
):
    """Initiate a phone call to a trucking company."""
    client = get_twilio_client()
    manager = get_call_manager()

    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Voice calling not configured")

    # Get provider info
    company = await CompanyRepo.get_by_id(request.provider_id)
    if not company:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not company.get("contact_phone"):
        raise HTTPException(status_code=400, detail="Provider has no phone number")

    # Create call tracking
    call = await manager.create_call(
        session_id=request.session_id or "",
        provider_id=request.provider_id,
        provider_name=company["name"],
        phone_number=company["contact_phone"],
        negotiation_context={
            "item_description": request.item_description,
            "target_price": request.target_price,
            "max_price": request.max_price,
            "user_id": user["id"],
        },
    )

    # Generate greeting
    greeting_action = await create_greeting(
        request.item_description,
        company["name"],
    )

    try:
        # Initiate Twilio call
        twilio_sid = await client.make_call(
            to_number=company["contact_phone"],
            call_id=call.call_id,
            greeting=greeting_action.message,
        )
        call.twilio_sid = twilio_sid
        await manager.update_status(call.call_id, CallStatus.RINGING)
        await manager.add_transcript_entry(call.call_id, "agent", greeting_action.message)

    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")
        await manager.update_status(call.call_id, CallStatus.FAILED)
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")

    return CallResponse(
        call_id=call.call_id,
        status=call.status.value,
        provider_name=company["name"],
        phone_number=company["contact_phone"],
    )


@router.get("/call/{call_id}")
async def get_call(call_id: str):
    """Get call status and transcript."""
    manager = get_call_manager()
    call = await manager.get_call(call_id)

    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    return call.to_dict()


@router.get("/call/{call_id}/stream")
async def stream_call(call_id: str):
    """Stream call updates via SSE."""
    manager = get_call_manager()
    call = await manager.get_call(call_id)

    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    async def event_generator():
        async for update in manager.subscribe(call_id):
            yield {"event": update.get("type", "update"), "data": json.dumps(update)}

    return EventSourceResponse(event_generator())


@router.post("/call/{call_id}/hangup")
async def hangup_call(call_id: str):
    """End an active call."""
    manager = get_call_manager()
    client = get_twilio_client()

    call = await manager.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.twilio_sid:
        try:
            await client.end_call(call.twilio_sid)
        except Exception as e:
            logger.error(f"Failed to end Twilio call: {e}")

    await manager.update_status(call_id, CallStatus.CANCELLED)
    return {"status": "cancelled", "call_id": call_id}


@router.post("/status/{call_id}")
async def twilio_status_callback(call_id: str, request: Request):
    """Handle Twilio status callbacks."""
    manager = get_call_manager()
    form = await request.form()

    status = form.get("CallStatus", "")
    logger.info(f"Twilio callback for {call_id}: {status}")

    status_map = {
        "initiated": CallStatus.INITIATING,
        "ringing": CallStatus.RINGING,
        "in-progress": CallStatus.CONNECTED,
        "answered": CallStatus.CONNECTED,
        "completed": CallStatus.COMPLETED,
        "busy": CallStatus.FAILED,
        "no-answer": CallStatus.FAILED,
        "failed": CallStatus.FAILED,
        "canceled": CallStatus.CANCELLED,
    }

    if status in status_map:
        await manager.update_status(call_id, status_map[status])

        # If call failed, record outcome
        if status in ("busy", "no-answer", "failed"):
            call = await manager.get_call(call_id)
            if call:
                await manager.complete_call(call_id, outcome=status)

    return Response(status_code=200)


@router.websocket("/stream/{call_id}")
async def voice_stream(websocket: WebSocket, call_id: str):
    """
    WebSocket for bidirectional audio streaming with Twilio.

    This handles the real-time audio stream from Twilio,
    processes speech-to-text, runs the negotiator AI,
    and sends text-to-speech responses back.
    """
    await websocket.accept()
    manager = get_call_manager()

    call = await manager.get_call(call_id)
    if not call:
        await websocket.close(code=4004, reason="Call not found")
        return

    await manager.update_status(call_id, CallStatus.NEGOTIATING)

    audio_buffer = bytearray()
    stream_sid = None
    silence_count = 0
    max_silence = 50  # Number of silent frames before processing

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info(f"Twilio stream connected for {call_id}")

            elif event == "start":
                stream_sid = data.get("start", {}).get("streamSid")
                logger.info(f"Stream started: {stream_sid}")

            elif event == "media":
                # Incoming audio from the human
                payload = data.get("media", {}).get("payload", "")
                if payload:
                    audio_chunk = base64_to_audio(payload)
                    audio_buffer.extend(audio_chunk)
                    silence_count = 0
                else:
                    silence_count += 1

                # Process when we detect end of speech (silence)
                if silence_count >= max_silence and len(audio_buffer) > 8000:
                    # Transcribe human speech
                    human_text = await transcribe_audio(bytes(audio_buffer))
                    audio_buffer.clear()
                    silence_count = 0

                    if human_text:
                        await manager.add_transcript_entry(call_id, "human", human_text)

                        # Get AI response
                        context = call.negotiation_context
                        action = await process_human_response(
                            item_description=context.get("item_description", ""),
                            target_price=context.get("target_price", 0),
                            max_price=context.get("max_price", 0),
                            provider_name=call.provider_name,
                            current_price=action.amount if 'action' in dir() else None,
                            transcript=[
                                {"role": t.role, "text": t.text}
                                for t in call.transcript
                            ],
                            human_said=human_text,
                        )

                        await manager.add_transcript_entry(call_id, "agent", action.message)

                        # Generate and send TTS audio
                        audio_response = await generate_speech(action.message)
                        audio_b64 = audio_to_base64(audio_response)

                        await websocket.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": audio_b64}
                        })

                        # Handle end of negotiation
                        if action.is_final:
                            if action.action == "accept":
                                await manager.complete_call(
                                    call_id,
                                    outcome="accepted",
                                    final_price=action.amount
                                )
                            else:
                                await manager.complete_call(
                                    call_id,
                                    outcome="rejected"
                                )
                            break

            elif event == "stop":
                logger.info(f"Stream stopped for {call_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {call_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {call_id}: {e}")
    finally:
        call = await manager.get_call(call_id)
        if call and call.status == CallStatus.NEGOTIATING:
            await manager.update_status(call_id, CallStatus.COMPLETED)


# Export router
voice_router = router
