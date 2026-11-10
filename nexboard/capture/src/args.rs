//! Aufruf: `deckbar-capture [--data DIR] [--history-dir DIR] [--lang en] [--device IFACE]
//! [--interval-ms 500] [--save-packets DIR] [--replay packets.txt [--realtime]]`

use std::path::PathBuf;
use std::time::Duration;

const DEFAULT_INTERVAL: Duration = Duration::from_millis(500);

pub struct Args {
    pub data_dir: PathBuf,
    pub history_dir: PathBuf,
    pub lang: String,
    pub device: Option<String>,
    pub interval: Duration,
    pub replay: Option<PathBuf>,
    pub realtime: bool,
    pub save_packets: Option<PathBuf>,
}

fn usage() -> ! {
    eprintln!(
        "deckbar-capture [--data DIR] [--history-dir DIR] [--lang en] [--device IFACE]\n\
         \x20               [--interval-ms 500] [--save-packets DIR] [--replay packets.txt [--realtime]]"
    );
    std::process::exit(2);
}

impl Args {
    pub fn parse() -> Self {
        let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
        let data_home =
            std::env::var_os("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|| home.join(".local/share"));
        let mut a = Args {
            data_dir: PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/a2tools/src/data")),
            history_dir: data_home.join("deckbar/aion2"),
            lang: "en".into(),
            device: None,
            interval: DEFAULT_INTERVAL,
            replay: None,
            realtime: false,
            save_packets: None,
        };
        let mut it = std::env::args().skip(1);
        while let Some(arg) = it.next() {
            let mut val = || it.next().unwrap_or_else(|| usage());
            match arg.as_str() {
                "--data" => a.data_dir = val().into(),
                "--history-dir" => a.history_dir = val().into(),
                "--lang" => a.lang = val(),
                "--device" => a.device = Some(val()),
                "--interval-ms" => a.interval = Duration::from_millis(val().parse().unwrap_or_else(|_| usage())),
                "--replay" => a.replay = Some(val().into()),
                "--realtime" => a.realtime = true,
                "--save-packets" => a.save_packets = Some(val().into()),
                _ => usage(),
            }
        }
        a
    }
}
