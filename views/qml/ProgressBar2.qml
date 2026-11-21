import QtQuick

// Barra di avanzamento con etichetta al centro (la parte piena cresce con un'animazione).
Rectangle {
    id: root
    property real value: 0
    property real maximum: 1
    property string label: ""
    implicitHeight: 20
    radius: 10
    color: Theme.bg
    border.width: 1
    border.color: Theme.border
    Rectangle {
        x: 1; y: 1; height: parent.height - 2
        width: Math.max(0, (parent.width - 2) * (root.maximum > 0 ? Math.min(1, root.value / root.maximum) : 0))
        radius: 9
        color: Theme.accentDim
        Behavior on width { NumberAnimation { duration: 500 * Theme.animScale; easing.type: Easing.OutCubic } }
    }
    Txt { anchors.centerIn: parent; text: root.label; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold }
}
