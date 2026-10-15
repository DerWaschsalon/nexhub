// NexBoard-Overlay: eine durchsichtige layer-shell-Fläche über dem ganzen Spielmonitor, darin die
// Widget-Seite des Daemons (web/overlay/). Eingabe-Region und Modus setzt deckbar-overlay (Python).
import QtQuick
import QtQuick.Window
import QtWebEngine
import QtWebChannel
import org.kde.layershell as LayerShell

Window {
    id: win
    visible: false  // erst zeigen, wenn Python Monitor und Eingabe-Region gesetzt hat
    color: "transparent"
    title: "NexBoard Overlay"

    LayerShell.Window.scope: "deckbar-overlay"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom
                               | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1  // Panels ignorieren, ganzer Monitor
    LayerShell.Window.activateOnShow: false
    // Monitor wählt deckbar-overlay (Einstellung oder Hauptmonitor laut KDE); QWindow::screen reicht nicht
    LayerShell.Window.screen: host.screen
    // Tastatur nur im Bearbeiten-Modus (Esc, Auswahlfelder), sonst nie: das Spiel behält den Fokus
    LayerShell.Window.keyboardInteractivity: host.mode === "edit"
        ? LayerShell.Window.KeyboardInteractivityOnDemand
        : LayerShell.Window.KeyboardInteractivityNone

    // Brücke für die Seite (QWebChannel-Objekt „bridge“)
    QtObject {
        id: bridge
        WebChannel.id: "bridge"
        property string mode: host.mode
        function setRegions(json) { host.setRegions(json) }
        function requestMode(m) { host.requestMode(m) }
        function finishEdit() { host.finishEdit() }
        function ready() { host.pageReady() }
        function call(cmd, json) { return host.call(cmd, json) }
        function log(s) { host.log(s) }
    }

    WebChannel {
        id: channel
        registeredObjects: [bridge]
    }

    WebEngineView {
        id: view
        objectName: "view"
        anchors.fill: parent
        backgroundColor: "transparent"
        webChannel: channel
        url: host.pageUrl
        // Erst zeigen, wenn die Seite sich gemeldet hat: Fehlerseiten (Daemon weg, Modul aus) wären
        // sonst bildschirmfüllend und undurchsichtig über dem Spiel
        visible: host.ready
        settings.showScrollBars: false
        settings.localStorageEnabled: true
        onJavaScriptConsoleMessage: (level, message, line, source) => host.log(message + " (" + source + ":" + line + ")")
        // Daemon noch nicht da (Autostart, Neustart): später erneut laden
        onLoadingChanged: (info) => {
            if (info.status === WebEngineView.LoadStartedStatus)
                host.pageGone()
            else if (info.status === WebEngineView.LoadFailedStatus)
                retry.start()
        }
        Timer {
            id: retry
            interval: 3000
            onTriggered: view.url = host.pageUrl
        }
    }
}
