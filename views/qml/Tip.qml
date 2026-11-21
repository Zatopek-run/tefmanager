import QtQuick
import QtQuick.Controls

// Suggerimento a comparsa nei colori del gioco (il ToolTip di serie è giallo chiaro).
ToolTip {
    id: root
    delay: 250
    timeout: 8000
    padding: 8
    contentItem: Txt {
        text: root.text
        font.pixelSize: Theme.fsSm
        wrapMode: Text.WordWrap
    }
    background: Rectangle {
        color: Theme.surface2
        border.color: Theme.borderStrong
        radius: 8
    }
}
