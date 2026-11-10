//! Der zusammengesetzte A2Tools-Kern: Daten, Rechner, Namen, Kampf-History und Treffer.
//!
//! So wie `app.rs` im Meter ihn aufbaut, ohne Oberfläche. Live und Replay teilen ihn.

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64};
use std::sync::{Arc, Weak};

use a2tools_dps_meter_lib::capture;
use a2tools_dps_meter_lib::capture::combat_port_detector::CombatPortDetector;
use a2tools_dps_meter_lib::combat::data_storage::DataStorage;
use a2tools_dps_meter_lib::combat::dps_calculator::DpsCalculator;
use a2tools_dps_meter_lib::combat::ping_tracker::PingTracker;
use a2tools_dps_meter_lib::history::fight_history::FightHistoryManager;
use a2tools_dps_meter_lib::i18n::lookup::{self, NpcLookup, SkillLookup};
use parking_lot::Mutex;
use tracing::warn;

use crate::args::Args;
use crate::frames::FrameTap;
use crate::game::GameCheck;
use crate::hits::HitLog;
use crate::out::{Message, Out};
use crate::view;

/// Was die DPS-Zeilen zeigen: Zeilen-Optionen und ob die volle DpsData mitkommt.
#[derive(Clone, Default)]
pub struct ViewSettings {
    pub rows: view::Options,
    pub full: bool,
}

pub struct Core {
    pub storage: Arc<DataStorage>,
    pub calc: Mutex<DpsCalculator>,
    pub skills: Arc<SkillLookup>,
    pub npcs: Arc<NpcLookup>,
    pub ping: Arc<PingTracker>,
    pub history: FightHistoryManager,
    pub hits: Arc<HitLog>,
    pub save_lock: Mutex<()>,
    pub data_dir: PathBuf,
    pub dot_ids: HashSet<i32>,
    pub suspended: Arc<AtomicBool>,
    pub ports: Option<Arc<CombatPortDetector>>, // nur im Live-Betrieb
    pub view: Mutex<ViewSettings>,
    /// Zählt jeden Befehl des Daemons: Sprache, Zielwahl, Reset … ändern die DpsData ohne neuen Schaden
    pub revision: AtomicU64,
    pub frames: FrameTap,
    pub game: GameCheck,
    pub out: Out,
}

impl Core {
    pub fn new(args: &Args, ping: Arc<PingTracker>, ports: Option<Arc<CombatPortDetector>>, out: Out) -> Arc<Self> {
        let skills = SkillLookup::new();
        let npcs = NpcLookup::new();
        lookup::load_language(&skills, &npcs, &args.data_dir, &args.lang);
        let (skills, npcs) = (Arc::new(skills), Arc::new(npcs));
        let storage = Arc::new(DataStorage::new());
        if let Ok(text) = std::fs::read_to_string(args.data_dir.join("abnormals.json")) {
            storage.set_abnormal_stack_limits(capture::abnormal::stack_limits(&text));
        }
        let _ = std::fs::create_dir_all(&args.history_dir);
        let core = Arc::new(Core {
            calc: Mutex::new(DpsCalculator::new(storage.clone(), skills.clone(), npcs.clone(), ping.clone())),
            frames: FrameTap::new(&storage, out.clone()),
            storage,
            skills,
            npcs,
            ping,
            history: FightHistoryManager::new(args.history_dir.clone()),
            hits: Arc::new(HitLog::new(&args.history_dir)),
            save_lock: Mutex::new(()),
            data_dir: args.data_dir.clone(),
            dot_ids: dot_skill_ids(args),
            suspended: Arc::new(AtomicBool::new(false)),
            ports,
            view: Mutex::default(),
            revision: AtomicU64::new(0),
            game: GameCheck::default(),
            out,
        });
        // Vor jedem Zurücksetzen der Kampfdaten (Zonenwechsel, Gruppenende) speichern, sonst
        // ginge alles seit dem letzten 30-s-Speichern verloren (wie im Meter, dort Issue #19).
        let weak: Weak<Core> = Arc::downgrade(&core);
        core.storage.set_before_reset(move || {
            if let Some(core) = weak.upgrade() {
                core.save(true);
            }
        });
        // Jeden Treffer mit eigenem Schaden mitschreiben (hits.rs)
        let hits = core.hits.clone();
        core.storage.set_on_hit(move |packet| hits.record(packet));
        core
    }

    /// Ein frischer Rechner auf denselben Daten, für Detailabfragen neben dem Live-Tick.
    pub fn reader(&self) -> DpsCalculator {
        DpsCalculator::new(self.storage.clone(), self.skills.clone(), self.npcs.clone(), self.ping.clone())
    }

    /// Bosskämpfe in die History. `force` auch laufende Kämpfe (vor Reset und beim Beenden).
    pub fn save(&self, force: bool) {
        let _saving = self.save_lock.lock();
        if self.storage.damage_generation() <= 0 {
            return;
        }
        let records = if force {
            self.calc.lock().snapshot_boss_fights_force()
        } else {
            match self.calc.try_lock() {
                Some(mut calc) => calc.snapshot_boss_fights(),
                None => return, // Tick rechnet gerade, nächstes Mal
            }
        };
        let mut ids = Vec::new();
        let summons = self.storage.get_summon_data();
        for record in &records {
            match self.history.save_fight(record) {
                Ok(()) => ids.push(record.id.clone()),
                Err(e) => warn!("Kampf {} nicht gespeichert: {e}", record.id),
            }
            if let Err(e) = self.hits.save_fight(record, &summons, &self.skills) {
                warn!("Treffer von Kampf {} nicht gespeichert: {e}", record.id);
            }
        }
        if !ids.is_empty() {
            self.out.send(&Message::FightsSaved { ids: &ids });
        }
    }

    pub fn reset(&self) {
        self.save(true);
        self.calc.lock().restart_target_selection(true);
        self.storage.forget_guessed_nicknames();
        self.storage.hide_party_placeholders();
    }
}

fn dot_skill_ids(args: &Args) -> HashSet<i32> {
    match std::fs::read_to_string(args.data_dir.join("dot_skill_ids.json")) {
        Ok(text) => serde_json::from_str::<Vec<i32>>(&text).unwrap_or_default().into_iter().collect(),
        Err(e) => {
            warn!("dot_skill_ids.json fehlt in {}: {e}", args.data_dir.display());
            HashSet::new()
        }
    }
}
