"""Branching primitives — ORM and history loader."""
import pytest
from sqlalchemy import delete, select

from src.models.enums import MessageRole
from src.models.orm import Conversation, Message
from src.services.agent_executor import AgentExecutor


async def _cleanup_conversation(session_factory, conversation_id):
    """Hard-delete a conversation + its messages.

    Tests in this file commit so a fresh session inside ``_load_active_branch``
    can see the data; that defeats the ``db_session`` rollback fixture, so the
    rows must be torn down explicitly. Cascade on Conversation.messages takes
    care of the message rows.
    """
    async with session_factory() as cleanup:
        await cleanup.execute(
            delete(Message).where(Message.conversation_id == conversation_id)
        )
        await cleanup.execute(
            delete(Conversation).where(Conversation.id == conversation_id)
        )
        await cleanup.commit()


@pytest.mark.asyncio
async def test_message_has_parent_message_id_field(db_session, seed_user):
    """Message rows can be linked into a parent chain."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.flush()

    root = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content="hello",
        sequence=0,
        parent_message_id=None,
    )
    db_session.add(root)
    await db_session.flush()

    child = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content="hi",
        sequence=1,
        parent_message_id=root.id,
    )
    db_session.add(child)
    await db_session.flush()

    fetched = (
        await db_session.execute(
            select(Message).where(Message.id == child.id)
        )
    ).scalar_one()
    assert fetched.parent_message_id == root.id


@pytest.mark.asyncio
async def test_conversation_has_active_leaf_and_instructions(db_session, seed_user):
    """Conversation tracks an active leaf and per-conversation instructions."""
    conv = Conversation(
        user_id=seed_user.id,
        channel="chat",
        instructions="Speak only in haiku.",
    )
    db_session.add(conv)
    await db_session.flush()

    msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content="hi",
        sequence=0,
    )
    db_session.add(msg)
    await db_session.flush()

    conv.active_leaf_message_id = msg.id
    await db_session.flush()

    fetched = (
        await db_session.execute(
            select(Conversation).where(Conversation.id == conv.id)
        )
    ).scalar_one()
    assert fetched.active_leaf_message_id == msg.id
    assert fetched.instructions == "Speak only in haiku."


@pytest.mark.asyncio
async def test_load_active_branch_returns_path_root_to_leaf(
    db_session, seed_user, async_session_factory
):
    """Active-branch loader returns messages from root to active leaf in order."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.flush()

    # Tree:
    #   m1 (user "hi")
    #   ├── m2 (assistant "hello")
    #   │     └── m3 (user "more")
    #   │           └── m4 (assistant "old reply")     <- old branch
    #   └── m2b (assistant "hey there")                <- new branch (retried)
    m1 = Message(conversation_id=conv.id, role=MessageRole.USER, content="hi", sequence=0)
    db_session.add(m1)
    await db_session.flush()
    m2 = Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content="hello",
                 sequence=1, parent_message_id=m1.id)
    db_session.add(m2)
    await db_session.flush()
    m3 = Message(conversation_id=conv.id, role=MessageRole.USER, content="more",
                 sequence=2, parent_message_id=m2.id)
    db_session.add(m3)
    await db_session.flush()
    m4 = Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content="old reply",
                 sequence=3, parent_message_id=m3.id)
    db_session.add(m4)
    await db_session.flush()
    m2b = Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content="hey there",
                  sequence=4, parent_message_id=m1.id)
    db_session.add(m2b)
    await db_session.flush()

    # Active leaf points at the new branch.
    conv.active_leaf_message_id = m2b.id
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)
        path = await executor._load_active_branch(conv)
        assert [m.content for m in path] == ["hi", "hey there"]
    finally:
        await _cleanup_conversation(async_session_factory, conv_id)


@pytest.mark.asyncio
async def test_load_active_branch_falls_back_to_max_sequence(
    db_session, seed_user, async_session_factory
):
    """If active_leaf is NULL, fall back to MAX(sequence) for legacy rows."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.flush()
    m1 = Message(conversation_id=conv.id, role=MessageRole.USER, content="hi", sequence=0)
    db_session.add(m1)
    await db_session.flush()
    m2 = Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content="hello",
                 sequence=1, parent_message_id=m1.id)
    db_session.add(m2)
    # active_leaf_message_id intentionally left NULL to simulate legacy data.
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)
        path = await executor._load_active_branch(conv)
        assert [m.content for m in path] == ["hi", "hello"]
    finally:
        await _cleanup_conversation(async_session_factory, conv_id)


@pytest.mark.asyncio
async def test_load_active_branch_empty_conversation(
    db_session, seed_user, async_session_factory
):
    """Empty conversation returns an empty path."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)
        path = await executor._load_active_branch(conv)
        assert path == []
    finally:
        await _cleanup_conversation(async_session_factory, conv_id)


@pytest.mark.asyncio
async def test_load_active_branch_breaks_cycles(
    db_session, seed_user, async_session_factory
):
    """A corrupt parent-chain cycle does not infinite-loop the loader."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.flush()
    m1 = Message(conversation_id=conv.id, role=MessageRole.USER, content="a", sequence=0)
    db_session.add(m1)
    await db_session.flush()
    m2 = Message(
        conversation_id=conv.id, role=MessageRole.ASSISTANT, content="b",
        sequence=1, parent_message_id=m1.id,
    )
    db_session.add(m2)
    await db_session.flush()
    # Inject a cycle: m1 → m2 → m1.
    m1.parent_message_id = m2.id
    conv.active_leaf_message_id = m2.id
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)
        path = await executor._load_active_branch(conv)
        # The walker terminates at the cycle. Two messages in either order is
        # acceptable; the contract is "doesn't hang or crash."
        assert len(path) == 2
        assert {m.content for m in path} == {"a", "b"}
    finally:
        # Break the cycle before deleting so the DELETE doesn't fight the FK.
        async with async_session_factory() as cleanup:
            await cleanup.execute(
                delete(Message).where(Message.conversation_id == conv_id)
            )
            await cleanup.execute(
                delete(Conversation).where(Conversation.id == conv_id)
            )
            await cleanup.commit()


@pytest.mark.asyncio
async def test_save_message_appends_to_active_branch(
    db_session, seed_user, async_session_factory
):
    """_save_message links the new row to the current leaf and advances it."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)

        m1 = await executor._save_message(
            conversation_id=conv_id,
            role=MessageRole.USER,
            content="hi",
        )
        async with async_session_factory() as session:
            fresh_conv = await session.get(Conversation, conv_id)
            assert fresh_conv is not None
            assert fresh_conv.active_leaf_message_id == m1.id
        assert m1.parent_message_id is None

        m2 = await executor._save_message(
            conversation_id=conv_id,
            role=MessageRole.ASSISTANT,
            content="hello",
        )
        async with async_session_factory() as session:
            fresh_conv = await session.get(Conversation, conv_id)
            assert fresh_conv is not None
            assert fresh_conv.active_leaf_message_id == m2.id
        assert m2.parent_message_id == m1.id
    finally:
        await _cleanup_conversation(async_session_factory, conv_id)


@pytest.mark.asyncio
async def test_save_message_with_parent_override_creates_sibling(
    db_session, seed_user, async_session_factory
):
    """parent_message_id_override creates a sibling under the chosen parent."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)
        u1 = await executor._save_message(
            conversation_id=conv_id, role=MessageRole.USER, content="hi",
        )
        a1 = await executor._save_message(
            conversation_id=conv_id, role=MessageRole.ASSISTANT, content="hello",
        )

        # Edit-style: a sibling user message under u1's parent (NULL).
        u1_edit = await executor._save_message(
            conversation_id=conv_id,
            role=MessageRole.USER,
            content="hi (edited)",
            parent_message_id_override=u1.parent_message_id,
        )
        assert u1_edit.parent_message_id == u1.parent_message_id  # both NULL
        # The leaf advanced to the new sibling.
        async with async_session_factory() as session:
            fresh_conv = await session.get(Conversation, conv_id)
            assert fresh_conv is not None
            assert fresh_conv.active_leaf_message_id == u1_edit.id

        # Retry-style: a sibling assistant under u1 (a1's parent).
        a1_retry = await executor._save_message(
            conversation_id=conv_id,
            role=MessageRole.ASSISTANT,
            content="hello (retry)",
            parent_message_id_override=a1.parent_message_id,
        )
        assert a1_retry.parent_message_id == u1.id
        async with async_session_factory() as session:
            fresh_conv = await session.get(Conversation, conv_id)
            assert fresh_conv is not None
            assert fresh_conv.active_leaf_message_id == a1_retry.id
    finally:
        await _cleanup_conversation(async_session_factory, conv_id)


@pytest.mark.asyncio
async def test_save_message_first_message_has_null_parent(
    db_session, seed_user, async_session_factory
):
    """First message in an empty conversation has NULL parent."""
    conv = Conversation(user_id=seed_user.id, channel="chat")
    db_session.add(conv)
    await db_session.commit()
    conv_id = conv.id

    try:
        executor = AgentExecutor(async_session_factory)
        m = await executor._save_message(
            conversation_id=conv_id, role=MessageRole.USER, content="first",
        )
        assert m.parent_message_id is None
    finally:
        await _cleanup_conversation(async_session_factory, conv_id)
