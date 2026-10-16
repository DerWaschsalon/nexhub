//! libpcap-Mitschnitt mit Kernel-Filter (BPF). Kopie von
//! `a2tools/src-tauri/src/capture/pcap_capturer.rs` (A2Tools v2.0.65, GPL-3.0; UPSTREAM_SHA unten =
//! sha256 der Datei, die ersten 16 Zeichen). Das Original liefert jedes Paket jedes Interfaces in
//! den Userspace, auch Downloads und den eigenen Verkehr auf localhost: Bei einem Download während
//! des Spiels läuft dann der Kanal zum Parser voll und es gehen Spielpakete verloren. Hier filtert
//! der Kernel:
//!
//!   - vor dem Port-Lock nur IPv4-TCP mit Nutzdaten (leere ACKs wirft der Parser ohnehin weg),
//!   - nach dem Lock nur noch den Spielport. Mehr wertet der CaptureDispatcher dann auch nicht aus
//!     (Port-Filter dort), auch das Umziehen auf ein anderes Interface braucht nur diesen Port.
//!     Fällt der Lock (Reset), wird der Filter wieder gelockert.
//!
//! Loopback bleibt drin: Relay-Tunnel von Ping-Reducern laufen dort, und A2Tools bevorzugt sie.
//! Ändert sich das Original, warnt `build.sh`; dann die Änderung hier nachziehen.

#[allow(dead_code)] // liest build.sh
pub const UPSTREAM_SHA: &str = "240f86584badc5aa";

use std::ffi::{c_char, c_int, c_long, c_uint, CStr, CString};
use std::ptr;
use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use libloading::{Library, Symbol};
use tokio::sync::mpsc;
use tracing::{error, info, warn};

use a2tools_dps_meter_lib::capture::captured_payload::CapturedPayload;
use a2tools_dps_meter_lib::capture::combat_port_detector::CombatPortDetector;
use a2tools_dps_meter_lib::platform;

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

// ===== Raw pcap FFI types =====

type PcapT = *mut std::ffi::c_void;
type PcapIfT = *mut PcapIf;

#[repr(C)]
struct PcapIf {
    next: *mut PcapIf,
    name: *const c_char,
    description: *const c_char,
    addresses: *mut PcapAddr,
    flags: c_uint,
}

#[repr(C)]
struct PcapAddr {
    next: *mut PcapAddr,
    addr: *mut SockAddr,
    netmask: *mut SockAddr,
    broadaddr: *mut SockAddr,
    dstaddr: *mut SockAddr,
}

#[repr(C)]
struct SockAddr {
    sa_family: u16,
    sa_data: [u8; 14],
}

/// `struct pcap_pkthdr`. The timestamp is a C `struct timeval`, two `long`s:
/// 32-bit on Windows, 64-bit on 64-bit Linux. Declaring them `i32` (as this
/// once did) reads `caplen` from the middle of the timestamp on Linux.
/// `struct bpf_program`
#[repr(C)]
struct BpfProgram {
    bf_len: c_uint,
    bf_insns: *mut std::ffi::c_void,
}

/// `PCAP_NETMASK_UNKNOWN`: Broadcast-Ausdrücke kommen im Filter nicht vor.
const NETMASK_UNKNOWN: c_uint = 0xffff_ffff;

#[repr(C)]
struct PcapPkthdr {
    ts_sec: c_long,
    ts_usec: c_long,
    caplen: c_uint,
    len: c_uint,
}

const PCAP_IF_LOOPBACK: c_uint = 0x00000001;

// ===== Device info =====

#[derive(Clone)]
struct DeviceInfo {
    name: String,
    description: String,
    has_addresses: bool,
    is_loopback: bool,
}

impl DeviceInfo {
    fn label(&self) -> &str {
        if self.description.is_empty() {
            &self.name
        } else {
            &self.description
        }
    }

    fn is_virtual(&self) -> bool {
        let label = self.label().to_lowercase();
        self.is_loopback
            || self.name.to_lowercase().contains("loopback")
            || label.contains("loopback")
            || label.contains("tap-windows")
            || label.contains("tap")
            || label.contains("wintun")
            || label.contains("wireguard")
    }
}

// ===== Pcap library wrapper =====

struct PcapLib {
    _lib: Library,
    findalldevs: unsafe extern "C" fn(*mut PcapIfT, *mut c_char) -> c_int,
    freealldevs: unsafe extern "C" fn(PcapIfT),
    open_live: unsafe extern "C" fn(*const c_char, c_int, c_int, c_int, *mut c_char) -> PcapT,
    close: unsafe extern "C" fn(PcapT),
    next_ex: unsafe extern "C" fn(PcapT, *mut *mut PcapPkthdr, *mut *const u8) -> c_int,
    datalink: unsafe extern "C" fn(PcapT) -> c_int,
    compile: unsafe extern "C" fn(PcapT, *mut BpfProgram, *const c_char, c_int, c_uint) -> c_int,
    setfilter: unsafe extern "C" fn(PcapT, *mut BpfProgram) -> c_int,
    freecode: unsafe extern "C" fn(*mut BpfProgram),
    geterr: unsafe extern "C" fn(PcapT) -> *const c_char,
}

impl PcapLib {
    fn load() -> Result<Self, String> {
        // The first of the OS's names for the library that loads.
        platform::pcap::prepare();
        let mut errors = Vec::new();
        let mut loaded = None;
        for name in platform::pcap::LIBRARIES {
            // SAFETY: loading libpcap runs no initialisation we depend on not running.
            match unsafe { Library::new(name) } {
                Ok(lib) => {
                    loaded = Some(lib);
                    break;
                }
                Err(e) => errors.push(format!("{name}: {e}")),
            }
        }
        let lib = loaded.ok_or_else(|| {
            format!(
                "Failed to load {}. {}\nError: {}",
                platform::pcap::LIBRARIES.join(" or "),
                platform::pcap::MISSING_HELP,
                errors.join("; ")
            )
        })?;

        unsafe {
            let findalldevs: Symbol<unsafe extern "C" fn(*mut PcapIfT, *mut c_char) -> c_int> =
                lib.get(b"pcap_findalldevs").map_err(|e| format!("pcap_findalldevs: {}", e))?;
            let freealldevs: Symbol<unsafe extern "C" fn(PcapIfT)> =
                lib.get(b"pcap_freealldevs").map_err(|e| format!("pcap_freealldevs: {}", e))?;
            let open_live: Symbol<
                unsafe extern "C" fn(*const c_char, c_int, c_int, c_int, *mut c_char) -> PcapT,
            > = lib.get(b"pcap_open_live").map_err(|e| format!("pcap_open_live: {}", e))?;
            let close: Symbol<unsafe extern "C" fn(PcapT)> =
                lib.get(b"pcap_close").map_err(|e| format!("pcap_close: {}", e))?;
            let next_ex: Symbol<
                unsafe extern "C" fn(PcapT, *mut *mut PcapPkthdr, *mut *const u8) -> c_int,
            > = lib.get(b"pcap_next_ex").map_err(|e| format!("pcap_next_ex: {}", e))?;
            let datalink: Symbol<unsafe extern "C" fn(PcapT) -> c_int> =
                lib.get(b"pcap_datalink").map_err(|e| format!("pcap_datalink: {}", e))?;
            let compile: Symbol<
                unsafe extern "C" fn(PcapT, *mut BpfProgram, *const c_char, c_int, c_uint) -> c_int,
            > = lib.get(b"pcap_compile").map_err(|e| format!("pcap_compile: {}", e))?;
            let setfilter: Symbol<unsafe extern "C" fn(PcapT, *mut BpfProgram) -> c_int> =
                lib.get(b"pcap_setfilter").map_err(|e| format!("pcap_setfilter: {}", e))?;
            let freecode: Symbol<unsafe extern "C" fn(*mut BpfProgram)> =
                lib.get(b"pcap_freecode").map_err(|e| format!("pcap_freecode: {}", e))?;
            let geterr: Symbol<unsafe extern "C" fn(PcapT) -> *const c_char> =
                lib.get(b"pcap_geterr").map_err(|e| format!("pcap_geterr: {}", e))?;

            Ok(Self {
                findalldevs: *findalldevs,
                freealldevs: *freealldevs,
                open_live: *open_live,
                close: *close,
                next_ex: *next_ex,
                datalink: *datalink,
                compile: *compile,
                setfilter: *setfilter,
                freecode: *freecode,
                geterr: *geterr,
                _lib: lib,
            })
        }
    }

    fn find_all_devs(&self) -> Result<Vec<DeviceInfo>, String> {
        let mut alldevs: PcapIfT = ptr::null_mut();
        let mut errbuf = [0u8; 256];

        let ret =
            unsafe { (self.findalldevs)(&mut alldevs, errbuf.as_mut_ptr() as *mut c_char) };

        if ret != 0 || alldevs.is_null() {
            let err = unsafe { CStr::from_ptr(errbuf.as_ptr() as *const c_char) }
                .to_string_lossy()
                .to_string();
            return Err(format!("pcap_findalldevs failed: {}", err));
        }

        let mut devices = Vec::new();
        let mut dev = alldevs;
        while !dev.is_null() {
            let d = unsafe { &*dev };
            let name = if d.name.is_null() {
                String::new()
            } else {
                unsafe { CStr::from_ptr(d.name) }
                    .to_string_lossy()
                    .to_string()
            };
            let description = if d.description.is_null() {
                String::new()
            } else {
                unsafe { CStr::from_ptr(d.description) }
                    .to_string_lossy()
                    .to_string()
            };
            let has_addresses = !d.addresses.is_null();
            let is_loopback = (d.flags & PCAP_IF_LOOPBACK) != 0;

            devices.push(DeviceInfo {
                name,
                description,
                has_addresses,
                is_loopback,
            });
            dev = d.next;
        }

        unsafe { (self.freealldevs)(alldevs) };
        Ok(devices)
    }

    fn open_live_handle(&self, name: &str) -> Result<PcapT, String> {
        let c_name = CString::new(name).map_err(|e| format!("Invalid device name: {}", e))?;
        let mut errbuf = [0u8; 256];

        let handle = unsafe {
            (self.open_live)(
                c_name.as_ptr(),
                65535,  // snaplen
                0,      // not promiscuous: only this machine's own traffic
                100,    // timeout ms
                errbuf.as_mut_ptr() as *mut c_char,
            )
        };

        if handle.is_null() {
            let err = unsafe { CStr::from_ptr(errbuf.as_ptr() as *const c_char) }
                .to_string_lossy()
                .to_string();
            return Err(format!("pcap_open_live failed: {}", err));
        }

        Ok(handle)
    }

    /// Kernel-Filter setzen. Nur aus dem Thread, der das Handle liest (pcap ist pro Handle nicht
    /// threadsicher).
    fn set_filter(&self, handle: PcapT, expr: &str) -> Result<(), String> {
        let c_expr = CString::new(expr).map_err(|e| e.to_string())?;
        let mut prog = BpfProgram { bf_len: 0, bf_insns: ptr::null_mut() };
        let err = || unsafe { CStr::from_ptr((self.geterr)(handle)) }.to_string_lossy().to_string();
        unsafe {
            if (self.compile)(handle, &mut prog, c_expr.as_ptr(), 1, NETMASK_UNKNOWN) != 0 {
                return Err(format!("pcap_compile: {}", err()));
            }
            let ret = (self.setfilter)(handle, &mut prog);
            (self.freecode)(&mut prog);
            if ret != 0 {
                return Err(format!("pcap_setfilter: {}", err()));
            }
        }
        Ok(())
    }
}

/// TCP-Segmente mit Nutzdaten: IP-Gesamtlänge minus IP- und TCP-Kopf. Bei Segmentation Offload
/// steht die Gesamtlänge auf 0; die Differenz läuft dann über (BPF rechnet vorzeichenlos) und das
/// Paket kommt durch, wie im Parser.
const HAS_PAYLOAD: &str = "(ip[2:2] - ((ip[0] & 0xf) << 2) - ((tcp[12] & 0xf0) >> 2)) != 0";

/// Filterausdruck: vor dem Lock alle TCP-Segmente mit Nutzdaten, danach nur der Spielport.
/// Auf Ethernet (Link-Typ 1) nimmt ein zweiter Zweig Frames mit VLAN-Tag mit (manche
/// Netzwerkkarten taggen jeden Frame, `vlan` verschiebt die Offsets für den Rest des Ausdrucks);
/// andere Link-Typen kennen `vlan` nicht.
pub fn bpf_filter(port: Option<u16>, link_type: c_int) -> String {
    let inner = match port {
        Some(p) => format!("ip and tcp port {p} and {HAS_PAYLOAD}"),
        None => format!("ip and tcp and {HAS_PAYLOAD}"),
    };
    if link_type == 1 { format!("({inner}) or (vlan and {inner})") } else { inner }
}

/// So oft schaut jeder Mitschnitt-Thread nach, ob sich der Port-Lock geändert hat.
const FILTER_CHECK_MS: u128 = 250;

// Safety: PcapLib function pointers are thread-safe (each thread gets its own pcap handle)
unsafe impl Send for PcapLib {}
unsafe impl Sync for PcapLib {}

/// Manages pcap device handles and captures TCP traffic from network interfaces.
/// Loads the OS's pcap library at runtime (`platform::pcap::LIBRARIES`) — no SDK
/// needed at compile time.
pub struct PcapCapturer {
    running: Arc<AtomicBool>,
    sender: mpsc::Sender<CapturedPayload>,
    shared: Arc<Shared>,
}

/// What the capture threads and the device watcher share.
#[derive(Default)]
struct Shared {
    /// Devices with a capture thread (or one about to start), by name. A
    /// thread takes its device out again when it ends, so a device that goes
    /// away and comes back (a VPN reconnecting) is captured again.
    active: Mutex<HashSet<String>>,
    /// Devices that could not be opened: not tried again, so the log does not
    /// repeat the failure every scan.
    failed: Mutex<HashSet<String>>,
    /// Packets lost because the parser had not taken the earlier ones yet.
    dropped: AtomicU64,
    /// Port-Erkennung des Dispatchers: ihr Lock bestimmt den Kernel-Filter (None = ungefiltert
    /// außer dem Nutzdaten-Filter).
    ports: Option<Arc<CombatPortDetector>>,
}

/// How often to look for network devices that appeared after the start: a
/// VPN or ping reducer (Mudfish's tap0, a WireGuard tunnel) connected while
/// the meter runs carries the game from then on.
const DEVICE_SCAN_MS: u64 = 15_000;

impl PcapCapturer {
    pub fn new(sender: mpsc::Sender<CapturedPayload>, ports: Option<Arc<CombatPortDetector>>) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            sender,
            shared: Arc::new(Shared { ports, ..Default::default() }),
        }
    }

    pub fn start(&self) {
        if self.running.swap(true, Ordering::SeqCst) {
            return;
        }

        let pcap = match PcapLib::load() {
            Ok(p) => Arc::new(p),
            Err(e) => {
                error!("{}", e);
                self.running.store(false, Ordering::SeqCst);
                return;
            }
        };

        let devices = match pcap.find_all_devs() {
            Ok(d) => d,
            Err(e) => {
                error!("Failed to list devices: {}", e);
                self.running.store(false, Ordering::SeqCst);
                return;
            }
        };

        // Only capture on devices that have addresses, and that this OS does not
        // rule out (Linux's catch-all "any" would duplicate every packet).
        let devices: Vec<_> = devices
            .into_iter()
            .filter(|d| d.has_addresses && !platform::pcap::skip_device(&d.name))
            .collect();

        if devices.is_empty() {
            error!("No capture devices found with addresses");
            self.running.store(false, Ordering::SeqCst);
            return;
        }

        info!("Found {} capture devices", devices.len());
        for (i, dev) in devices.iter().enumerate() {
            info!(
                "  [{}] {} (loopback={}, addresses={})",
                i,
                dev.label(),
                dev.is_loopback,
                dev.has_addresses
            );
        }

        let virtual_devices: Vec<_> = devices.iter().filter(|d| d.is_virtual()).cloned().collect();
        let physical_devices: Vec<_> = devices.iter().filter(|d| !d.is_virtual()).cloned().collect();

        // Every device is claimed now, so the watcher below does not start a
        // second thread on a physical device still waiting for its delay.
        {
            let mut active = self.shared.active.lock().unwrap_or_else(|p| p.into_inner());
            active.extend(devices.iter().map(|d| d.name.clone()));
        }

        // Start virtual/loopback devices first
        for device in &virtual_devices {
            start_capture_thread(
                device.clone(),
                pcap.clone(),
                self.sender.clone(),
                self.running.clone(),
                self.shared.clone(),
            );
        }

        if virtual_devices.is_empty() {
            // No virtual devices — start physical immediately
            for device in &physical_devices {
                start_capture_thread(
                    device.clone(),
                    pcap.clone(),
                    self.sender.clone(),
                    self.running.clone(),
                    self.shared.clone(),
                );
            }
        } else {
            // Start physical after delay as fallback
            let running = self.running.clone();
            let sender = self.sender.clone();
            let pcap2 = pcap.clone();
            let shared = self.shared.clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(1500));
                if !running.load(Ordering::SeqCst) {
                    return;
                }
                for device in &physical_devices {
                    info!("Starting capture on physical device: {}", device.label());
                    start_capture_thread(
                        device.clone(),
                        pcap2.clone(),
                        sender.clone(),
                        running.clone(),
                        shared.clone(),
                    );
                }
            });
        }

        // Devices that appear later, and lost packets.
        let running = self.running.clone();
        let sender = self.sender.clone();
        let shared = self.shared.clone();
        std::thread::spawn(move || {
            let mut reported_drops = 0;
            while running.load(Ordering::SeqCst) {
                std::thread::sleep(std::time::Duration::from_millis(DEVICE_SCAN_MS));
                let dropped = shared.dropped.load(Ordering::Relaxed);
                if dropped > reported_drops {
                    warn!(
                        "{} packets lost in the last {} s: the parser fell behind the capture",
                        dropped - reported_drops,
                        DEVICE_SCAN_MS / 1000
                    );
                    reported_drops = dropped;
                }
                let Ok(devices) = pcap.find_all_devs() else { continue };
                for device in devices {
                    if !device.has_addresses || platform::pcap::skip_device(&device.name) {
                        continue;
                    }
                    if shared.failed.lock().unwrap_or_else(|p| p.into_inner()).contains(&device.name) {
                        continue;
                    }
                    if !shared.active.lock().unwrap_or_else(|p| p.into_inner()).insert(device.name.clone()) {
                        continue;
                    }
                    info!("New capture device: {} (loopback={})", device.label(), device.is_loopback);
                    start_capture_thread(device, pcap.clone(), sender.clone(), running.clone(), shared.clone());
                }
            }
        });
    }

    #[allow(dead_code)] // wie im Original, hier beendet das Programm den Mitschnitt
    pub fn stop(&self) {
        self.running.store(false, Ordering::SeqCst);
    }

    #[allow(dead_code)]
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

/// List available capture device labels (for the settings UI dropdown).
pub fn list_device_labels() -> Result<Vec<String>, String> {
    let pcap = PcapLib::load().map_err(|e| e.to_string())?;
    let devices = pcap.find_all_devs().map_err(|e| e.to_string())?;
    Ok(devices
        .into_iter()
        .filter(|d| d.has_addresses && !platform::pcap::skip_device(&d.name))
        .map(|d| d.label().to_string())
        .collect())
}

fn start_capture_thread(
    device: DeviceInfo,
    pcap: Arc<PcapLib>,
    sender: mpsc::Sender<CapturedPayload>,
    running: Arc<AtomicBool>,
    shared: Arc<Shared>,
) {
    let label = device.label().to_string();
    let dev_name = device.name.clone();

    std::thread::spawn(move || {
        let release = |failed: bool| {
            shared.active.lock().unwrap_or_else(|p| p.into_inner()).remove(&dev_name);
            if failed {
                shared.failed.lock().unwrap_or_else(|p| p.into_inner()).insert(dev_name.clone());
            }
        };
        let handle = match pcap.open_live_handle(&dev_name) {
            Ok(h) => h,
            Err(e) => {
                warn!("Failed to open capture on {}: {}", label, e);
                release(true);
                return;
            }
        };

        let link_type = unsafe { (pcap.datalink)(handle) };
        info!("Capture active on {} (link type {})", label, link_type);

        // Kernel-Filter: None = noch keiner gesetzt, Some(lock) = für diesen Lock gesetzt.
        // Schlägt er fehl, läuft der Mitschnitt ungefiltert weiter wie im Original.
        let mut filtered_for: Option<Option<u16>> = None;
        let mut filter_failed = false;
        let mut last_check = std::time::Instant::now();
        let mut apply_filter = |lock: Option<u16>| {
            if filter_failed || filtered_for == Some(lock) {
                return;
            }
            match pcap.set_filter(handle, &bpf_filter(lock, link_type)) {
                Ok(()) => {
                    info!("Filter on {}: {}", label, lock.map_or("TCP with payload".to_string(), |p| format!("port {p}")));
                    filtered_for = Some(lock);
                }
                Err(e) => {
                    warn!("No kernel filter on {} ({}), capturing unfiltered", label, e);
                    filter_failed = true;
                }
            }
        };
        apply_filter(shared.ports.as_ref().and_then(|p| p.current_port()));

        while running.load(Ordering::SeqCst) {
            if last_check.elapsed().as_millis() >= FILTER_CHECK_MS {
                last_check = std::time::Instant::now();
                apply_filter(shared.ports.as_ref().and_then(|p| p.current_port()));
            }

            let mut header: *mut PcapPkthdr = ptr::null_mut();
            let mut data: *const u8 = ptr::null();

            let ret = unsafe { (pcap.next_ex)(handle, &mut header, &mut data) };

            match ret {
                1 => {
                    let hdr = unsafe { &*header };
                    let len = hdr.caplen as usize;
                    // Use pcap hardware timestamp (seconds + microseconds since epoch)
                    let pcap_ts_ms = (hdr.ts_sec as i64) * 1000 + (hdr.ts_usec as i64) / 1000;
                    // Sanity check: if pcap timestamp looks bogus, fall back to wall clock
                    let ts = if pcap_ts_ms > 1_000_000_000_000 && pcap_ts_ms < 2_000_000_000_000 {
                        pcap_ts_ms
                    } else {
                        now_ms()
                    };
                    let frame = unsafe { std::slice::from_raw_parts(data, len) };
                    if let Some(mut payload) = parse_tcp_payload(frame, link_type, &label) {
                        payload.captured_at_ms = ts;
                        if sender.try_send(payload).is_err() {
                            shared.dropped.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                }
                0 => continue, // Timeout
                -2 => break,   // EOF (savefile)
                _ => {
                    warn!("Capture error on {} (ret={})", label, ret);
                    break;
                }
            }
        }

        unsafe { (pcap.close)(handle) };
        info!("Capture stopped on {}", label);
        release(false);
    });
}

/// Where IPv4 starts in a frame of pcap link type `link_type`, or `None` if this
/// frame is not IPv4 under that type. Link types are libpcap's (DLT_*/LINKTYPE_*),
/// the same on every OS.
fn link_header_len(link_type: c_int, frame: &[u8]) -> Option<usize> {
    let be16 = |at: usize| frame.get(at..at + 2).map(|b| u16::from_be_bytes([b[0], b[1]]));
    match link_type {
        // Ethernet, with up to two 802.1Q / 802.1ad VLAN tags (some NICs, e.g.
        // Realtek with "Priority & VLAN" on, tag every frame).
        1 => {
            let mut at = 12;
            for _ in 0..2 {
                match be16(at)? {
                    0x8100 | 0x88A8 => at += 4,
                    _ => break,
                }
            }
            (be16(at)? == 0x0800).then_some(at + 2)
        }
        // BSD loopback / Npcap loopback: 4-byte address family, AF_INET = 2.
        0 => (frame.get(..4)? == [2, 0, 0, 0]).then_some(4),
        // Raw IP (VPN and tunnel adapters, WireGuard).
        12 | 14 | 101 | 228 => Some(0),
        // Linux "cooked" capture v1: protocol at bytes 14-15, 16-byte header.
        113 => (be16(14)? == 0x0800).then_some(16),
        // Linux "cooked" capture v2: protocol at bytes 0-1, 20-byte header.
        276 => (be16(0)? == 0x0800).then_some(20),
        _ => None,
    }
}

/// The original guess at the link layer, from the frame alone. Kept as the
/// fallback so nothing that parsed before the link type was consulted can stop
/// parsing now.
fn guess_link_header_len(frame: &[u8]) -> Option<usize> {
    if frame.len() >= 14 {
        let ether_type = u16::from_be_bytes([frame[12], frame[13]]);
        if ether_type == 0x0800 {
            Some(14) // Standard Ethernet
        } else if frame[0] == 2 && frame[1] == 0 && frame[2] == 0 && frame[3] == 0 {
            Some(4) // NULL/Loopback: AF_INET (little-endian 2) = IPv4
        } else if (frame[0] >> 4) == 4 {
            Some(0) // Raw IPv4
        } else {
            None
        }
    } else if (frame[0] >> 4) == 4 {
        Some(0) // Raw IPv4 (short frame)
    } else {
        None
    }
}

/// Parse raw captured frame to extract TCP payload. The link type says where
/// IPv4 starts; when it does not fit, the frame-only guess gets a chance.
fn parse_tcp_payload(frame: &[u8], link_type: c_int, device_name: &str) -> Option<CapturedPayload> {
    if frame.len() < 4 {
        return None;
    }
    let ip_offset = link_header_len(link_type, frame)
        .filter(|&at| frame.get(at).is_some_and(|b| b >> 4 == 4))
        .or_else(|| guess_link_header_len(frame))?;

    if frame.len() < ip_offset + 20 {
        return None;
    }
    let ip_header = &frame[ip_offset..];
    if ip_header[0] >> 4 != 4 {
        return None;
    }
    let ip_header_len = ((ip_header[0] & 0x0F) as usize) * 4;
    if ip_header[9] != 6 {
        return None; // Not TCP
    }

    // Kept as numbers: formatting them as text cost two allocations for
    // every packet on every device, and nothing reads them as text.
    let src_ip = std::net::Ipv4Addr::new(ip_header[12], ip_header[13], ip_header[14], ip_header[15]);
    let dst_ip = std::net::Ipv4Addr::new(ip_header[16], ip_header[17], ip_header[18], ip_header[19]);

    let tcp_offset = ip_offset + ip_header_len;
    if frame.len() < tcp_offset + 20 {
        return None;
    }
    let tcp_header = &frame[tcp_offset..];
    let src_port = u16::from_be_bytes([tcp_header[0], tcp_header[1]]);
    let dst_port = u16::from_be_bytes([tcp_header[2], tcp_header[3]]);
    let tcp_seq = u32::from_be_bytes([tcp_header[4], tcp_header[5], tcp_header[6], tcp_header[7]]);
    let tcp_ack =
        u32::from_be_bytes([tcp_header[8], tcp_header[9], tcp_header[10], tcp_header[11]]);
    let tcp_header_len = ((tcp_header[12] >> 4) as usize) * 4;

    // The payload ends where the IP packet says it does, not at the end of the
    // frame: Ethernet pads short frames to 60 bytes, so a bare ACK carries 6
    // padding bytes after its TCP header. Most network cards pad with zeros,
    // which the framing skips; some pad with whatever was in the buffer, and
    // those bytes landed in the game stream and threw the framing off. One
    // player's meter read 77% of a boss's damage while their party member's,
    // in the same fight, read all of it (2026-10-06). A total length of 0
    // (segmentation offload) or past the frame keeps the frame's end.
    let ip_total_len = u16::from_be_bytes([ip_header[2], ip_header[3]]) as usize;
    let ip_end = ip_offset + ip_total_len;
    let end = if ip_total_len >= ip_header_len + 20 && ip_end <= frame.len() { ip_end } else { frame.len() };
    let payload_offset = tcp_offset + tcp_header_len;
    if payload_offset >= end {
        return None;
    }
    let payload = &frame[payload_offset..end];
    if payload.is_empty() {
        return None;
    }

    Some(CapturedPayload {
        src_port,
        dst_port,
        data: payload.to_vec(),
        device_name: Some(device_name.to_string()),
        captured_at_ms: now_ms(),
        src_ip: Some(src_ip),
        dst_ip: Some(dst_ip),
        tcp_seq,
        tcp_ack,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// IPv4 + TCP from 10.0.0.2:51000 to 193.202.112.99:13328, payload "hi".
    fn ipv4_tcp() -> Vec<u8> {
        let mut ip = vec![0x45, 0, 0, 42, 0, 0, 0, 0, 64, 6, 0, 0, 10, 0, 0, 2, 193, 202, 112, 99];
        let tcp = [0xC7, 0x38, 0x34, 0x10, 0, 0, 0, 1, 0, 0, 0, 0, 0x50, 0x18, 0, 0, 0, 0, 0, 0];
        ip.extend_from_slice(&tcp);
        ip.extend_from_slice(b"hi");
        ip
    }

    fn check(link_type: c_int, header: &[u8]) {
        let frame = [header, &ipv4_tcp()].concat();
        let p = parse_tcp_payload(&frame, link_type, "dev").expect("parsed");
        assert_eq!((p.src_port, p.dst_port), (51000, 13328), "link type {link_type}");
        assert_eq!(p.dst_ip, Some(std::net::Ipv4Addr::new(193, 202, 112, 99)));
        assert_eq!(p.data, b"hi");
    }

    #[test]
    fn reads_every_link_layer_the_meter_meets() {
        let ether = [[0u8; 12].as_slice(), &[0x08, 0x00]].concat();
        check(1, &ether); // Ethernet / Wi-Fi
        let vlan = [[0u8; 12].as_slice(), &[0x81, 0x00, 0x00, 0x05, 0x08, 0x00]].concat();
        check(1, &vlan); // Ethernet with an 802.1Q tag
        check(0, &[2, 0, 0, 0]); // Npcap / BSD loopback
        check(12, &[]); // raw IP (VPN, WireGuard)
        check(101, &[]);
        let sll = [[0u8; 14].as_slice(), &[0x08, 0x00]].concat();
        check(113, &sll); // Linux cooked v1
        let sll2 = [[0x08u8, 0x00].as_slice(), &[0u8; 18]].concat();
        check(276, &sll2); // Linux cooked v2
    }

    #[test]
    fn an_unknown_or_mismatched_link_type_still_gets_the_old_guess() {
        // Ethernet framing reported as some other link type: guessed as before.
        let ether = [[0u8; 12].as_slice(), &[0x08, 0x00]].concat();
        check(999, &ether);
        // Raw IP on a device that claims Ethernet: the exact read fails, the
        // guess finds IPv4 at 0, as it always did.
        check(1, &[]);
    }

    #[test]
    fn ethernet_padding_is_not_payload() {
        // A bare ACK (IP total length 40) padded to 60 bytes with non-zero
        // bytes, as one player's network card sends them (2026-10-06).
        let ether = [[0u8; 12].as_slice(), &[0x08, 0x00]].concat();
        let mut ack = ipv4_tcp();
        ack.truncate(40);
        ack[3] = 40;
        let frame = [ether.as_slice(), &ack, &[0xbe, 0xde, 0x00, 0x03, 0x66, 0xfd]].concat();
        assert!(parse_tcp_payload(&frame, 1, "dev").is_none());

        // Data followed by padding keeps only the data.
        let mut short = ipv4_tcp();
        short.truncate(41);
        short[3] = 41;
        let frame = [ether.as_slice(), &short, &[0xbe, 0xde, 0x00, 0x03, 0x66]].concat();
        assert_eq!(parse_tcp_payload(&frame, 1, "dev").unwrap().data, b"h");

        // A total length of 0 (segmentation offload) keeps the frame's end.
        let mut tso = ipv4_tcp();
        tso[2] = 0;
        tso[3] = 0;
        let frame = [ether.as_slice(), &tso].concat();
        assert_eq!(parse_tcp_payload(&frame, 1, "dev").unwrap().data, b"hi");
    }

    #[test]
    fn filters_compile_for_every_link_type() {
        // Ohne Rechte: pcap_open_dead liefert ein Handle nur zum Kompilieren.
        let lib = PcapLib::load().expect("libpcap");
        let open_dead: Symbol<unsafe extern "C" fn(c_int, c_int) -> PcapT> =
            unsafe { lib._lib.get(b"pcap_open_dead") }.expect("pcap_open_dead");
        // DLT-Werte, wie pcap_datalink sie unter Linux liefert (101 ist nur ein Dateiformat-Wert)
        for link in [1, 12, 113, 276] {
            let h = unsafe { open_dead(link, 65535) };
            assert!(!h.is_null());
            for port in [None, Some(13328)] {
                let expr = bpf_filter(port, link);
                let c = CString::new(expr.clone()).unwrap();
                let mut prog = BpfProgram { bf_len: 0, bf_insns: ptr::null_mut() };
                let ret = unsafe { (lib.compile)(h, &mut prog, c.as_ptr(), 1, NETMASK_UNKNOWN) };
                assert_eq!(ret, 0, "link {link}: {expr}");
                unsafe { (lib.freecode)(&mut prog) };
            }
            unsafe { (lib.close)(h) };
        }
    }

    #[test]
    fn non_ipv4_frames_are_ignored() {
        let arp = [[0u8; 12].as_slice(), &[0x08, 0x06], &[0u8; 28]].concat();
        assert!(parse_tcp_payload(&arp, 1, "dev").is_none());
    }
}
