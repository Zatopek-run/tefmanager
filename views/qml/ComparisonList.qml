import QtQuick
import QtQuick.Layouts

// Confronto con gli atleti della stessa disciplina: barre proporzionali al valore complessivo, l'atleta in evidenza.
ColumnLayout {
    id: root
    property var comparison: ({ rows: [], top: 1 })
    spacing: 4
    Repeater {
        model: comparison.rows
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Txt { Layout.preferredWidth: 24; text: modelData.rank + "°"; color: modelData.me ? Theme.accent : Theme.textFaint; font.pixelSize: Theme.fsSm; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignRight }
            Txt { Layout.preferredWidth: 150; text: modelData.name; elide: Text.ElideRight; font.pixelSize: Theme.fsSm + 1; font.weight: modelData.me ? Font.Bold : Font.Normal
                  color: modelData.me ? Theme.text : Theme.textMuted }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 10; radius: 5; color: Theme.bg
                Rectangle {
                    height: parent.height; radius: 5; color: modelData.me ? Theme.accent : Theme.borderStrong
                    width: parent.width * modelData.ovr / Math.max(1, comparison.top)
                    Behavior on width { NumberAnimation { duration: 500 * Theme.animScale; easing.type: Easing.OutCubic } }
                }
            }
            Txt { Layout.preferredWidth: 28; text: modelData.ovr; horizontalAlignment: Text.AlignRight; font.weight: Font.Bold; font.pixelSize: Theme.fsSm + 1
                  color: modelData.me ? Theme.accent : Theme.text }
        }
    }
}
