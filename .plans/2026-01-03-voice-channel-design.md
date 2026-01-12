# Voice Channel Design (Twilio ConversationRelay)

**Status**: Approved
**Date**: 2026-01-03

## Overview

Add Twilio ConversationRelay as a voice channel for Bifrost agents. Callers dial a phone number, get routed to an agent, and have a natural voice conversation. The agent can use tools (workflows) and transfer calls.

## Architecture

```
Caller dials +1-555-0001
         ↓
Twilio webhook: POST /api/voice/incoming (To=+15550001)
         ↓
Lookup VoiceNumber by phone_number → get agent pool, org context
         ↓
Return TwiML with ConversationRelay WebSocket URL
         ↓
Twilio connects: WS /api/voice/relay/{voice_number_id}
         ↓
VoiceHandler creates Conversation (channel="voice")
         ↓
Route to agent (single agent = direct, multiple = AI routing on first utterance)
         ↓
AgentExecutor.chat() → VoiceHandler translates chunks to Twilio messages
         ↓
Twilio TTS → Caller hears response
```

## Data Model

### VoiceNumber

```python
class VoiceNumber(Base):
    __tablename__ = "voice_numbers"

    id: UUID
    organization_id: UUID | None  # None = global (platform-level)

    # Twilio identifiers
    phone_number: str  # E.164: "+15550001"
    phone_sid: str  # Twilio's PN SID for API calls

    # Display
    name: str  # "Sales Line", "Main Support"

    # Routing
    default_agent_id: UUID  # FK → Agent (fallback, or sole agent if only one)

    # Voice configuration
    greeting: str | None  # "Hi, thanks for calling Acme..."
    tts_provider: str  # "google" | "amazon" | "elevenlabs" (default: elevenlabs)
    voice_id: str  # Default: "OYTbf65OHHFELVut7v2H" (Hope)
    language: str  # Default: "en-US"

    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Relationships
    agents: list[Agent]  # via voice_number_agents junction
```

### VoiceNumberAgent (Junction)

```python
class VoiceNumberAgent(Base):
    __tablename__ = "voice_number_agents"

    voice_number_id: UUID  # FK
    agent_id: UUID  # FK
    created_at: datetime
```

### Twilio Credentials (SystemConfig)

Stored in `system_configs` table following the LLM config pattern:

```python
# category="twilio", key="provider_config", organization_id=None
{
    "account_sid": "AC...",
    "encrypted_auth_token": "..."  # Fernet encrypted
}
```

### Config Change

Rename `BIFROST_MCP_BASE_URL` → `BIFROST_PUBLIC_URL` for all public webhook URLs.

## Agent Routing

Routing is implicit based on agent count:

| Agents assigned | Behavior |
|-----------------|----------|
| 1 agent | Always use that agent |
| 2+ agents | AI routes first message among pool, fallback to `default_agent_id` |

```python
if len(voice_number.agents) == 1:
    agent = voice_number.agents[0]
else:
    agent = await route_to_agent(voice_number.agents, first_message)
    if agent is None:
        agent = voice_number.default_agent
```

## Voice Handler

Wraps `AgentExecutor.chat()` and translates streaming chunks to Twilio messages:

```python
class VoiceHandler:
    async def handle_relay(self, websocket: WebSocket, voice_number: VoiceNumber):
        call_sid = None
        conversation = None
        agent = None

        while websocket is open:
            msg = await websocket.receive_json()

            if msg["type"] == "setup":
                call_sid = msg["callSid"]
                conversation = await self._create_conversation(
                    voice_number=voice_number,
                    call_sid=call_sid,
                    channel="voice",
                )
                if len(voice_number.agents) == 1:
                    agent = voice_number.agents[0]

            elif msg["type"] == "prompt":
                user_text = msg["voicePrompt"]

                # Route on first message if multiple agents
                if agent is None:
                    agent = await self._route_to_agent(
                        voice_number.agents,
                        user_text,
                        voice_number.default_agent,
                    )

                # Stream through AgentExecutor
                async for chunk in self.executor.chat(
                    agent=agent,
                    conversation=conversation,
                    user_message=user_text,
                    stream=True,
                ):
                    await self._send_to_twilio(websocket, chunk)

            elif msg["type"] == "interrupt":
                # Caller interrupted - log for analytics
                pass

    async def _send_to_twilio(self, websocket, chunk):
        if chunk.type == "delta":
            await websocket.send_json({
                "type": "text",
                "token": chunk.content,
                "last": False
            })
        elif chunk.type == "done":
            await websocket.send_json({
                "type": "text",
                "token": "",
                "last": True
            })
        # tool_call chunks: agent naturally announces tool usage via prompt
```

## Voice Tools

System tools available to voice agents:

### transfer_call

```python
{
    "name": "transfer_call",
    "description": "Transfer the caller to another phone number",
    "parameters": {
        "destination": "string - phone number to transfer to (E.164)",
        "reason": "string - brief summary for the recipient"
    }
}
```

Transfer destinations are configured in the agent's system prompt:
> "You can transfer calls. Available destinations: Sales (+1-555-1234), Billing (+1-555-5678). Use your judgment based on the caller's request."

When `transfer_call` is invoked, VoiceHandler sends:
```json
{"type": "end", "handoffData": {"reason": "...", "destination": "..."}}
```

Twilio then POSTs to action URL, which returns TwiML to dial the destination.

### end_call

```python
{
    "name": "end_call",
    "description": "End the call politely",
    "parameters": {
        "farewell": "string - final message before hanging up"
    }
}
```

## API Endpoints

### Twilio Config (Platform Admin)

```
POST   /api/voice/config           # Save Twilio credentials
GET    /api/voice/config           # Get config (masked)
DELETE /api/voice/config           # Remove config
POST   /api/voice/config/test      # Test connection
```

### Phone Number Management

```
GET    /api/voice/numbers/available     # Search purchasable numbers
POST   /api/voice/numbers               # Purchase + configure number
GET    /api/voice/numbers               # List configured numbers
GET    /api/voice/numbers/{id}          # Get number details
PATCH  /api/voice/numbers/{id}          # Update config
DELETE /api/voice/numbers/{id}          # Release number
```

### Twilio Webhooks (Internal)

```
POST   /api/voice/incoming              # Incoming call → return TwiML
POST   /api/voice/status                # Call status updates
POST   /api/voice/action/{call_sid}     # Post-transfer callback
WS     /api/voice/relay/{number_id}     # ConversationRelay WebSocket
```

## TwiML Response

When a call comes in:

```xml
<Response>
  <Connect>
    <ConversationRelay
      url="wss://{BIFROST_PUBLIC_URL}/api/voice/relay/{voice_number_id}"
      ttsProvider="elevenlabs"
      voice="OYTbf65OHHFELVut7v2H"
      language="en-US"
      welcomeGreeting="Hi, thanks for calling Acme..." />
  </Connect>
</Response>
```

## Files to Create

### New Files

```
api/src/models/orm/voice.py              # VoiceNumber, VoiceNumberAgent
api/src/models/contracts/voice.py        # Pydantic DTOs
api/src/routers/voice.py                 # All voice endpoints
api/src/services/voice_handler.py        # WebSocket handler
api/src/services/twilio_config_service.py # Credential management
api/src/services/twilio_client.py        # SDK wrapper

api/alembic/versions/xxx_add_voice_tables.py

api/tests/unit/services/test_voice_handler.py
api/tests/integration/api/test_voice.py
```

### Modified Files

```
api/src/main.py                          # Register voice router
api/src/models/orm/__init__.py           # Export new models
api/src/config.py                        # Rename MCP_BASE_URL → PUBLIC_URL
```

## UI Notes

- Voice ID field: free text input
- Link to [Twilio voice docs](https://www.twilio.com/docs/voice/conversationrelay/voice-configuration#elevenlabs-voices) for voice selection
- Defaults: ElevenLabs, Hope voice, en-US

## Not in Scope (v1)

- Outbound calling
- Call recording/storage
- Multi-party calls / conferencing
- IVR menu builder
- SMS channel
- Voicemail
- BYOT (Bring Your Own Twilio) - orgs use platform account

## Success Criteria

1. Platform admin configures Twilio credentials
2. Search and purchase phone number via API
3. Assign agent(s) to number, configure greeting and voice
4. Call the number, hear greeting, speak to agent
5. Agent can call workflow tools naturally ("Let me look that up...")
6. Say "transfer me to sales" → get connected to number from agent prompt
7. Call ends gracefully with `end_call` tool
