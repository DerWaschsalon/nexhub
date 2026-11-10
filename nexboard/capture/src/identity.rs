//! Identität des eigenen Charakters, wie die gleichnamigen Tauri-Commands in `app.rs` des Meters.

use crate::core::Core;

/// Ab dieser ID stehen Platzhalterzeilen der Gruppe, keine echten Figuren
const PARTY_PLACEHOLDER_ID: i64 = 90_000_000;

impl Core {
    pub fn set_character_name(&self, name: &str, manual: bool) {
        // Hat das Spiel den Namen schon genannt, gilt nur noch ein von Hand eingetragener.
        if self.storage.local_identity_from_self_record() && !manual {
            return;
        }
        let trimmed = name.trim().to_string();
        self.storage.set_local_character_name(Some(name.to_string()));
        if !trimmed.is_empty()
            && (manual || !self.storage.local_id_from_scope())
            && let Some(id) = self.storage.local_player_id()
        {
            self.storage.set_permanent_nickname(id as i32, &trimmed);
        }
    }

    pub fn bind_local_actor_id(&self, actor_id: i64, manual: bool) {
        if !self.storage.ui_may_bind_local_id(actor_id, manual) {
            return;
        }
        if actor_id <= 0 {
            self.storage.set_local_player_id(None);
            return;
        }
        if self.storage.local_player_id() != Some(actor_id) {
            self.storage.set_local_player_id(Some(actor_id));
        }
        if self.storage.local_id_from_scope() {
            return;
        }
        if let Some(name) = self.storage.local_character_name() {
            let trimmed = name.trim();
            if !trimmed.is_empty() && self.storage.get_nickname(actor_id as i32).as_deref() != Some(trimmed) {
                self.storage.set_permanent_nickname(actor_id as i32, trimmed);
            }
        }
    }

    pub fn bind_local_nickname(&self, actor_id: i64, nickname: &str) {
        let current = self.storage.get_nickname(actor_id as i32);
        if self.storage.local_player_id() == Some(actor_id) && current.as_deref() == Some(nickname) {
            return;
        }
        if actor_id >= PARTY_PLACEHOLDER_ID {
            return;
        }
        if self.storage.local_id_from_scope() && self.storage.local_player_id() == Some(actor_id) {
            return;
        }
        if self.storage.local_identity_from_self_record() {
            return;
        }
        self.storage.set_local_player_id(Some(actor_id));
        self.storage.set_permanent_nickname(actor_id as i32, nickname);
    }
}
