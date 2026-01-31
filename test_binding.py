import asyncio
import logging
from core.session_binding import SessionBindingManager

# Setup basic logging
logging.basicConfig(level=logging.INFO)

async def test_session_binding():
    print("--- Starting SessionBindingManager Test ---")
    mgr = SessionBindingManager()
    
    chat_id = "test_chat_123"
    account_id = "acc_001"
    session_id = "projects/123/locations/global/sessions/sess_abc"
    
    # 1. Test Setting Binding with Session ID
    print(f"Setting binding: {chat_id} -> {account_id}, {session_id}")
    await mgr.set_binding(chat_id, account_id, session_id)
    
    # 2. Test Retrieving Binding
    binding = await mgr.get_binding(chat_id)
    print(f"Retrieved binding: {binding}")
    
    assert binding is not None
    assert binding["account_id"] == account_id
    assert binding["session_id"] == session_id
    print("✅ Retrieval Verified")
    
    # 3. Test Updating Binding (without session_id, should ideally preserve it - check implementation behavior)
    # Based on my code: if not session_id and old_binding...: final_session_id = old_binding.get("session_id")
    print("Updating binding without explicit session_id (should preserve)")
    await mgr.set_binding(chat_id, account_id) # No session_id passed
    
    binding_updated = await mgr.get_binding(chat_id)
    print(f"Retrieved updated binding: {binding_updated}")
    
    assert binding_updated["session_id"] == session_id
    print("✅ Preservation Verified")
    
    # 4. Test Updating Binding (with NEW session_id)
    new_session_id = "projects/123/locations/global/sessions/sess_xyz"
    print(f"Updating binding with NEW session_id: {new_session_id}")
    await mgr.set_binding(chat_id, account_id, new_session_id)
    
    binding_new = await mgr.get_binding(chat_id)
    print(f"Retrieved new binding: {binding_new}")
    
    assert binding_new["session_id"] == new_session_id
    print("✅ Update Verified")

    # 5. Remove binding
    await mgr.remove_binding(chat_id)
    binding_removed = await mgr.get_binding(chat_id)
    assert binding_removed is None
    print("✅ Removal Verified")

if __name__ == "__main__":
    asyncio.run(test_session_binding())
