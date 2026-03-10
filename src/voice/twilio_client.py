"""Twilio client for making outbound voice calls."""
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Say
from ..config import get_settings, logger


class TwilioVoiceClient:
    """Wrapper for Twilio voice API."""

    def __init__(self):
        settings = get_settings()
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.phone_number = settings.twilio_phone_number
        self.server_url = settings.server_url
        self._client = None

    @property
    def client(self) -> Client:
        """Lazy-load Twilio client."""
        if self._client is None:
            if not self.account_sid or not self.auth_token:
                raise ValueError("Twilio credentials not configured")
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check if Twilio is properly configured."""
        return bool(self.account_sid and self.auth_token and self.phone_number)

    async def make_call(
        self,
        to_number: str,
        call_id: str,
        greeting: str = "Hello, this is an AI assistant calling to discuss freight rates."
    ) -> str:
        """
        Initiate an outbound call with media streaming.

        Args:
            to_number: Phone number to call (E.164 format)
            call_id: Unique identifier for this call session
            greeting: Initial greeting message

        Returns:
            Twilio call SID
        """
        if not self.is_configured:
            raise ValueError("Twilio not configured")

        # Generate TwiML for the call
        twiml = self._generate_twiml(call_id, greeting)

        try:
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                twiml=twiml,
                status_callback=f"{self.server_url}/api/voice/status/{call_id}",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                status_callback_method="POST",
            )
            logger.info(f"Call initiated: {call.sid} to {to_number}")
            return call.sid
        except Exception as e:
            logger.error(f"Failed to initiate call: {e}")
            raise

    def _generate_twiml(self, call_id: str, greeting: str) -> str:
        """Generate TwiML for bidirectional audio streaming."""
        response = VoiceResponse()

        # Say greeting first
        response.say(greeting, voice="Polly.Matthew")

        # Connect to WebSocket for bidirectional streaming
        connect = Connect()
        stream = Stream(
            url=f"wss://{self.server_url.replace('https://', '').replace('http://', '')}/api/voice/stream/{call_id}"
        )
        stream.parameter(name="call_id", value=call_id)
        connect.append(stream)
        response.append(connect)

        return str(response)

    def generate_response_twiml(self, message: str, call_id: str, end_call: bool = False) -> str:
        """Generate TwiML for responding during a call."""
        response = VoiceResponse()
        response.say(message, voice="Polly.Matthew")

        if not end_call:
            # Continue streaming
            connect = Connect()
            stream = Stream(
                url=f"wss://{self.server_url.replace('https://', '').replace('http://', '')}/api/voice/stream/{call_id}"
            )
            connect.append(stream)
            response.append(connect)
        else:
            response.hangup()

        return str(response)

    async def end_call(self, call_sid: str) -> None:
        """End an active call."""
        try:
            self.client.calls(call_sid).update(status="completed")
            logger.info(f"Call ended: {call_sid}")
        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}")
            raise

    async def get_call_status(self, call_sid: str) -> dict:
        """Get current status of a call."""
        try:
            call = self.client.calls(call_sid).fetch()
            return {
                "sid": call.sid,
                "status": call.status,
                "duration": call.duration,
                "direction": call.direction,
                "from": call.from_,
                "to": call.to,
            }
        except Exception as e:
            logger.error(f"Failed to get call status: {e}")
            raise


# Singleton instance
_twilio_client: TwilioVoiceClient | None = None


def get_twilio_client() -> TwilioVoiceClient:
    """Get the Twilio client singleton."""
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = TwilioVoiceClient()
    return _twilio_client
