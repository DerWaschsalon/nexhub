//! DPS-Zeilen an den Daemon, nur bei Änderung.
//!
//! `dps` (Zeilen wie im Stream-Overlay, view.rs) ist klein und wird jedes Mal gebaut und verglichen.
//! Die volle DpsData (`dps_data`, bis ~100 KB, nur solange jemand sie braucht) wird erst serialisiert,
//! wenn sich einer der Zähler geändert hat, an denen der Kern selbst seinen Zwischenstand misst
//! (`DpsCalculator::get_dps`), oder etwas, das er danach noch einträgt (`finalize_rows`).

use std::sync::atomic::Ordering;

use a2tools_dps_meter_lib::entity::dps_data::DpsData;

use crate::core::Core;
use crate::out::Message;
use crate::view;

/// Alles, wovon die volle DpsData abhängt. Gleich = dieselben Daten wie beim letzten Mal.
#[derive(PartialEq)]
struct DataKey {
    damage: i64,
    names: u64,
    party_rows: bool,
    local_id: Option<i64>,
    party: u64,
    zones: (u64, u64),
    target: (i32, String),
    // Gruppenmitglieder mit Merkmalen, die finalize_rows nachträgt (Unterstützer, A2Tools-Nutzer)
    marks: Vec<(i32, bool, bool)>,
    revision: u64, // Befehle (Sprache, Zielwahl, Reset …), siehe Core::revision
}

impl DataKey {
    fn of(core: &Core, dps: &DpsData) -> Self {
        let mut marks: Vec<_> = dps.map.iter().map(|(&id, row)| (id, row.is_supporter, row.uses_a2tools)).collect();
        marks.sort_unstable();
        Self {
            damage: core.storage.damage_generation(),
            names: core.storage.names_generation(),
            party_rows: core.storage.party_placeholders_wanted(),
            local_id: dps.local_player_id,
            party: dps.party_generation,
            zones: (dps.zone_generation, dps.instance_generation),
            target: (dps.target_id, dps.target_mode.clone()),
            marks,
            revision: core.revision.load(Ordering::Relaxed),
        }
    }
}

#[derive(Default)]
pub struct Ticker {
    last_view: String,
    last_data: Option<DataKey>,
}

impl Ticker {
    pub fn tick(&mut self, core: &Core) {
        let dps = core.calc.lock().get_dps();
        let settings = core.view.lock().clone();
        let view = view::build(&dps, &settings.rows);
        // Klein genug, um es als Text zu vergleichen: gleiche Zeile = keine Meldung (wie bisher)
        if let Ok(text) = serde_json::to_string(&view)
            && text != self.last_view
        {
            core.out.send(&Message::Dps { view: &view });
            self.last_view = text;
        }
        if !settings.full {
            self.last_data = None; // beim nächsten Einschalten sofort ein Stand
            return;
        }
        let key = DataKey::of(core, &dps);
        if self.last_data.as_ref() != Some(&key) {
            core.out.send(&Message::DpsData { data: &dps });
            self.last_data = Some(key);
        }
    }
}
