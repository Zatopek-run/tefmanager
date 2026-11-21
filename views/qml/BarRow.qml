import QtQuick
import QtQuick.Layouts

// Una caratteristica: etichetta, barra colorata per livello, valore.
RowLayout {
    id: root
    property var info: ({})
    readonly property color tone: info.level === "great" ? Theme.good : info.level === "good" ? Theme.warn : info.level === "mid" ? Theme.orange : Theme.bad
    spacing: 10
    Txt { Layout.preferredWidth: 118; text: info.label || ""; color: Theme.textMuted; font.pixelSize: Theme.fsSm + 1; elide: Text.ElideRight }
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 8; radius: 4; color: Theme.bg
        Rectangle {
            height: parent.height; radius: 4; color: root.tone
            width: parent.width * Math.max(0, Math.min(100, info.value || 0)) / 100
            Behavior on width { NumberAnimation { duration: 500 * Theme.animScale; easing.type: Easing.OutCubic } }
        }
    }
    Txt { Layout.preferredWidth: 30; horizontalAlignment: Text.AlignRight; text: info.value !== undefined ? info.value : ""; font.weight: Font.Bold; font.pixelSize: Theme.fsSm + 1 }
}
