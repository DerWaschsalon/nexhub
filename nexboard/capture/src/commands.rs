//! Befehle des Daemons (stdin, eine JSON-Zeile je Befehl) als Typen.
//!
//! `{"id":1,"cmd":"details","target_id":…}` → `Command::Details`. Die Befehle der Meter-Oberfläche
//! verhalten sich wie die gleichnamigen Tauri-Commands in `a2tools/src-tauri/src/app.rs`.

use std::sync::Arc;
use std::sync::atomic::Ordering;

use a2tools_dps_meter_lib::capture::pcap_capturer as pcap;
use a2tools_dps_meter_lib::history::fight_history::is_plain_name;
use a2tools_dps_meter_lib::i18n::lookup;
use serde::Deserialize;
use serde_json::{Value, json};
use tokio::io::AsyncBufReadExt;

use crate::core::Core;
use crate::effects;
use crate::out::{Message, Reply};

const MAX_ROWS: u64 = 24;

fn yes() -> bool {
    true
}

#[derive(Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case")]
enum Command {
    Snapshot,
    Reset,
    Save,
    Context,
    History,
    CaptureStatus,
    WindowTitle,
    Devices,
    ResetDetection,
    ActiveEffects,
    PluginDecoders {
        plugins: Vec<Value>,
    },
    SubscribeFrames {
        opcodes: Vec<u16>,
    },
    TargetMode {
        mode: String,
    },
    Details {
        target_id: i32,
        actor_ids: Option<Vec<i32>>,
        #[serde(default)]
        summary: bool,
    },
    Buffs {
        target_id: i32,
        #[serde(default)]
        target_ids: Vec<i32>,
    },
    Fight {
        fight_id: String,
    },
    DeleteFight {
        fight_id: String,
    },
    SetDevice {
        device: String,
    },
    SetCharacterName {
        name: String,
        #[serde(default)]
        manual: bool,
    },
    BindLocalActorId {
        actor_id: i64,
        #[serde(default)]
        manual: bool,
    },
    BindLocalNickname {
        actor_id: i64,
        nickname: String,
    },
    Suspend {
        #[serde(default = "yes")]
        on: bool,
    },
    View {
        limit: Option<u64>,
        pin_you: Option<bool>,
        full: Option<bool>,
    },
    Language {
        lang: String,
    },
}

fn to_value(v: impl serde::Serialize) -> Result<Value, String> {
    serde_json::to_value(v).map_err(|e| e.to_string())
}

impl Core {
    /// Eine Befehlszeile ausführen; die Antwort trägt die `id` der Anfrage.
    pub fn answer(&self, line: &str) -> Reply {
        let request: Value = match serde_json::from_str(line) {
            Ok(v) => v,
            Err(e) => return Reply::new(Value::Null, Err(format!("kein JSON: {e}"))),
        };
        let id = request.get("id").cloned().unwrap_or(Value::Null);
        let outcome = serde_json::from_value::<Command>(request).map_err(|e| e.to_string()).and_then(|c| self.run(c));
        self.revision.fetch_add(1, Ordering::Relaxed);
        Reply::new(id, outcome)
    }

    fn run(&self, command: Command) -> Result<Value, String> {
        match command {
            Command::Snapshot => to_value(self.calc.lock().get_dps()),
            Command::Reset => {
                self.reset();
                Ok(Value::Null)
            }
            Command::Save => {
                self.save(true);
                Ok(Value::Null)
            }
            Command::Context => to_value(self.reader().get_details_context()),
            Command::History => to_value(self.history.list_fights()),
            Command::CaptureStatus => Ok(self.capture_status()),
            Command::WindowTitle => Ok(json!(self.game.title())),
            Command::Devices => Ok(json!(pcap::list_device_labels().unwrap_or_default())),
            Command::ResetDetection => {
                if let Some(p) = &self.ports {
                    p.reset();
                }
                self.ping.reset();
                Ok(Value::Null)
            }
            Command::ActiveEffects => Ok(effects::active(self)),
            Command::PluginDecoders { plugins } => Ok(self.frames.set_decoders(&plugins)),
            Command::SubscribeFrames { opcodes } => {
                self.frames.subscribe(&opcodes);
                Ok(Value::Null)
            }
            Command::TargetMode { mode } => {
                self.calc.lock().set_target_selection_mode(&mode);
                Ok(Value::Null)
            }
            Command::Details { target_id, actor_ids, summary } => {
                let reader = self.reader();
                if summary {
                    to_value(reader.get_hover_details(target_id, actor_ids.as_deref()))
                } else {
                    to_value(reader.get_target_details(target_id, actor_ids.as_deref()))
                }
            }
            // alle Ziele, die die Details zusammen zeigen (ihre Stagger-Fenster gehören dazu)
            Command::Buffs { target_id, target_ids } => {
                to_value(self.reader().live_fight_buffs(target_id, &target_ids))
            }
            Command::Fight { fight_id } => to_value(self.history.load_fight(&fight_id)?),
            Command::DeleteFight { fight_id } => {
                self.delete_fight(&fight_id)?;
                Ok(Value::Null)
            }
            Command::SetDevice { device } => {
                let device = device.trim().to_string();
                if let Some(p) = &self.ports {
                    p.set_preferred_device((!device.is_empty()).then_some(device));
                }
                Ok(Value::Null)
            }
            Command::SetCharacterName { name, manual } => {
                self.set_character_name(&name, manual);
                Ok(Value::Null)
            }
            Command::BindLocalActorId { actor_id, manual } => {
                self.bind_local_actor_id(actor_id, manual);
                Ok(Value::Null)
            }
            Command::BindLocalNickname { actor_id, nickname } => {
                self.bind_local_nickname(actor_id, &nickname);
                Ok(Value::Null)
            }
            Command::Suspend { on } => {
                self.suspended.store(on, Ordering::SeqCst);
                Ok(Value::Null)
            }
            Command::View { limit, pin_you, full } => {
                let mut view = self.view.lock();
                if let Some(n) = limit {
                    view.rows.limit = n.clamp(1, MAX_ROWS) as usize;
                }
                view.rows.pin_you = pin_you.unwrap_or(view.rows.pin_you);
                view.full = full.unwrap_or(view.full);
                Ok(Value::Null)
            }
            Command::Language { lang } => {
                lookup::load_language(&self.skills, &self.npcs, &self.data_dir, &lang);
                Ok(Value::Null)
            }
        }
    }

    fn delete_fight(&self, id: &str) -> Result<(), String> {
        if !is_plain_name(id) {
            return Err(format!("ungültige Kampf-ID {id:?}"));
        }
        let _saving = self.save_lock.lock();
        self.history.delete_fight(id)?;
        self.hits.delete_fight(id);
        Ok(())
    }

    fn capture_status(&self) -> Value {
        let port = self.ports.as_ref().and_then(|p| p.current_port());
        let device = self.ports.as_ref().and_then(|p| p.current_device());
        json!({
            "locked": port.is_some(),
            "port": port,
            "device": device.clone().unwrap_or_default(),
            "ip": device.unwrap_or_else(|| "127.0.0.1".to_string()),
            "localPlayerId": self.storage.local_player_id(),
            "characterName": self.storage.local_character_name(),
            "characterNameFromGame": self.storage.local_identity_from_self_record(),
        })
    }
}

/// Befehle von stdin, jeder in einem eigenen Arbeits-Thread. EOF = Daemon weg.
pub async fn read_stdin(core: Arc<Core>) {
    let mut lines = tokio::io::BufReader::new(tokio::io::stdin()).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        if line.trim().is_empty() {
            continue;
        }
        let core = core.clone();
        tokio::task::spawn_blocking(move || {
            let reply = core.answer(line.trim());
            core.out.send(&Message::Reply(&reply));
        });
    }
}
