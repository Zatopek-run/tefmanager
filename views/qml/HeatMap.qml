import QtQuick
import QtQuick.Layouts

// Dove gli atleti sono forti e deboli: una cella per atleta e gara, indaco (debole) → turchese → oro (forte); l'anello segna la specialità.
Item {
    id: root
    property var heat: null
    readonly property int rowH: 32
    readonly property int nameW: 168
    readonly property int rows: heat ? heat.rows.length : 3
    implicitHeight: 28 + rows * rowH + 30

    function mix(a, b, t) { return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1) }
    function heatColor(l) {
        var c0 = Qt.color(Theme.heatCold), c1 = Qt.color(Theme.heatMid), c2 = Qt.color(Theme.heatHot)
        return l < 0.5 ? mix(c0, c1, l / 0.5) : mix(c1, c2, (l - 0.5) / 0.5)
    }
    function textOn(c) { return (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) * 255 > 150 ? "#0a0f1f" : Theme.text }

    Txt { anchors.centerIn: parent; visible: !root.heat; text: "Nessun atleta da confrontare: tessera i primi atleti."; color: Theme.textMuted; font.pixelSize: Theme.fsSm }

    Item {
        anchors.fill: parent
        visible: !!root.heat
        // intestazioni delle gare
        Row {
            x: root.nameW; height: 28; width: parent.width - root.nameW
            Repeater {
                model: root.heat ? root.heat.events : []
                Item { width: parent.width / (root.heat ? root.heat.events.length : 1); height: 28
                    Txt { anchors.centerIn: parent; text: modelData; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold; color: Theme.textMuted } }
            }
        }
        Column {
            y: 28; width: parent.width
            Repeater {
                model: root.heat ? root.heat.rows : []
                Item {
                    id: rowItem
                    property int r: index
                    property int cols: modelData.cells.length
                    width: parent.width; height: root.rowH
                    Txt { x: 0; width: root.nameW - 10; height: parent.height; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                          text: modelData.name; font.pixelSize: Theme.fsSm; color: modelData.injured ? Theme.textFaint : Theme.text }
                    Row {
                        x: root.nameW; width: parent.width - root.nameW; height: parent.height
                        Repeater {
                            model: modelData.cells
                            Item {
                                id: cell
                                width: parent.width / rowItem.cols; height: root.rowH
                                Rectangle {
                                    id: box
                                    anchors { fill: parent; margins: 2 }
                                    radius: Theme.radiusSm
                                    color: root.heatColor(modelData.level)
                                    border.width: modelData.best ? 1.6 : 0
                                    border.color: Theme.text
                                    scale: cma.containsMouse ? 1.06 : 1.0
                                    opacity: appear
                                    property real appear: 1
                                    Behavior on scale { NumberAnimation { duration: 120 * Theme.animScale } }
                                    Txt { anchors.centerIn: parent; text: modelData.score; font.pixelSize: Theme.fsSm; font.weight: Font.Bold; color: root.textOn(box.color) }
                                    Component.onCompleted: {
                                        if (Theme.animScale > 0) { appear = 0; fade.start() }
                                    }
                                    SequentialAnimation {
                                        id: fade
                                        PauseAnimation { duration: (rowItem.r * 30 + index * 25) * Theme.animScale }
                                        NumberAnimation { target: box; property: "appear"; to: 1; duration: 300 * Theme.animScale }
                                    }
                                }
                                MouseArea { id: cma; anchors.fill: parent; hoverEnabled: true }
                                Tip { visible: cma.containsMouse; text: modelData.tip; x: cma.mouseX + 12; y: cma.mouseY + 16 }
                            }
                        }
                    }
                }
            }
        }
        // legenda
        Row {
            x: root.nameW + 4; y: 28 + root.rows * root.rowH + 8
            spacing: 8
            Txt { text: "debole"; font.pixelSize: Theme.fsXs; color: Theme.textFaint }
            Rectangle { width: 160; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.heatCold }
                    GradientStop { position: 0.5; color: Theme.heatMid }
                    GradientStop { position: 1.0; color: Theme.heatHot } } }
            Txt { text: "forte · anello = specialità"; font.pixelSize: Theme.fsXs; color: Theme.textFaint }
        }
    }
}
