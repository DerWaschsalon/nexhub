// Prototyp: eine layer-shell-Fläche über dem ganzen Monitor, darin die Widget-Seite.
import QtQuick
import QtQuick.Window
import QtWebEngine
import QtWebChannel
import org.kde.layershell as LayerShell

Window {
    id: win
    visible: false  // erst zeigen, wenn Python Monitor und Eingabe-Region gesetzt hat
    color: "transparent"
    title: "DeckBar Overlay"

    LayerShell.Window.scope: "deckbar-overlay"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom
                               | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1  // Panels ignorieren, ganzer Monitor
    LayerShell.Window.activateOnShow: false
    // Tastatur nur im Bearbeiten-Modus (für Esc), sonst nie: das Spiel behält den Fokus
    LayerShell.Window.keyboardInteractivity: host.mode === "edit"
        ? LayerShell.Window.KeyboardInteractivityOnDemand
        : LayerShell.Window.KeyboardInteractivityNone

    // Brücke für die Seite (QWebChannel-Objekt „bridge“)
    QtObject {
        id: bridge
        WebChannel.id: "bridge"
        property string mode: host.mode
        property string meterUrl: host.meterUrl
        function setClickRects(json) { host.setClickRects(json) }
        function requestMode(m) { host.requestMode(m) }
        function loadLayout() { return host.loadLayout() }
        function saveLayout(json) { host.saveLayout(json) }
        function log(s) { host.log(s) }
    }

    WebChannel {
        id: channel
        registeredObjects: [bridge]
    }

    WebEngineView {
        id: view
        anchors.fill: parent
        backgroundColor: "transparent"
        webChannel: channel
        url: host.pageUrl
        settings.localContentCanAccessRemoteUrls: true
        settings.showScrollBars: false
        // Namenseffekt in der Meter-Oberfläche (iframe, anderer Ursprung): Skript in Unterfenster
        Component.onCompleted: userScripts.collection = [{
            name: "deckbar-frame-effects",
            sourceCode: host.frameScript,
            injectionPoint: WebEngineScript.DocumentReady,
            worldId: WebEngineScript.MainWorld,
            runsOnSubFrames: true
        }]
        onJavaScriptConsoleMessage: (level, message, line, source) => host.log(message + " (" + source + ":" + line + ")")
    }
}
