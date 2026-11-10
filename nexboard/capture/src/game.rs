//! Läuft das Spiel? Titel wie `find_aion2_window_title` des Meters.
//!
//! Die Suche liest ganz /proc. Status (alle 2 s) und `window_title` (fragt jede offene Meter-Seite
//! alle 3 s) teilen sich deshalb ein Ergebnis je `FRESH`.

use std::time::{Duration, Instant};

use a2tools_dps_meter_lib::platform;
use parking_lot::Mutex;

pub const FRESH: Duration = Duration::from_secs(2);

#[derive(Default)]
pub struct GameCheck {
    last: Mutex<Option<(Instant, Option<String>)>>,
}

impl GameCheck {
    pub fn title(&self) -> Option<String> {
        let mut last = self.last.lock();
        match &*last {
            Some((at, title)) if at.elapsed() < FRESH => title.clone(),
            _ => {
                let title = platform::window_detector::find_aion2_window_title();
                *last = Some((Instant::now(), title.clone()));
                title
            }
        }
    }
}
