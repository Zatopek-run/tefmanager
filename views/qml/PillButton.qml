import QtQuick

// Pulsante secondario del design system.
Rectangle {
    id: root
    property string text: ""
    signal clicked()
    implicitHeight: 34
    implicitWidth: label.implicitWidth + 32
    radius: Theme.radiusMd
    color: ma.pressed ? Theme.bg : (ma.containsMouse ? "#1f2d64" : Theme.surface2)
    border.width: 1
    border.color: ma.containsMouse ? Theme.accent : Theme.borderStrong
    Behavior on color { ColorAnimation { duration: 120 * Theme.animScale } }
    Txt { id: label; anchors.centerIn: parent; text: root.text; font.weight: Font.DemiBold }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
}
