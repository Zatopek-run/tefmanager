import QtQuick

// La stagione in una riga: una casella per settimana, gare in rilievo, Preparazione attenuata, «oggi» evidenziato, nomi delle fasi sotto.
Item {
    id: root
    property var weeks: []
    property var phases: []
    readonly property real padX: 6
    readonly property real step: weeks.length > 0 ? (width - 2 * padX) / weeks.length : 1
    readonly property real baseY: 40
    implicitHeight: 84

    function phaseIndex(i) {
        var n = -1
        for (var k = 0; k <= i; k++) if (weeks[k].phaseStart) n++
        return n
    }

    Repeater {
        model: root.weeks
        Item {
            id: cell
            property real h: modelData.race ? 30 : 14
            x: root.padX + index * root.step
            width: root.step
            height: root.baseY + 30
            Rectangle {
                id: bar
                x: 0; width: Math.max(2, root.step - 2)
                y: root.baseY - cell.h; height: cell.h
                radius: 3
                opacity: modelData.past ? 0.38 : 1
                color: modelData.race ? Theme.accent : modelData.prep ? Qt.rgba(0.37, 0.43, 0.59, 0.5) : Theme.borderStrong
                property real grow: 1
                transform: Scale { origin.y: bar.height; yScale: bar.grow }
                Component.onCompleted: { if (Theme.animScale > 0) { grow = 0; up.start() } }
                SequentialAnimation { id: up
                    PauseAnimation { duration: index * 12 * Theme.animScale }
                    NumberAnimation { target: bar; property: "grow"; to: 1; duration: 320 * Theme.animScale; easing.type: Easing.OutBack } }
            }
            Rectangle {   // anello «oggi»
                visible: modelData.current
                x: -2; width: Math.max(2, root.step - 2) + 4
                y: root.baseY - cell.h - 2; height: cell.h + 4
                radius: 4; color: "transparent"; border.width: 2; border.color: Theme.text
                SequentialAnimation on opacity { running: modelData.current && Theme.animScale > 0; loops: Animation.Infinite
                    NumberAnimation { to: 0.45; duration: 900 } NumberAnimation { to: 1.0; duration: 900 } }
            }
            Rectangle {   // freccia sopra
                visible: modelData.current
                width: 8; height: 8; rotation: 45; color: Theme.text
                x: bar.width / 2 - 4; y: root.baseY - cell.h - 14
            }
            Rectangle {   // inizio fase
                visible: modelData.phaseStart
                x: -1; y: root.baseY + 5; width: 1; height: 17; color: Theme.textFaint
            }
            Txt {
                visible: modelData.phaseStart && root.phaseIndex(index) >= 0 && root.phaseIndex(index) < root.phases.length
                x: 3; y: root.baseY + 6
                text: visible ? root.phases[root.phaseIndex(index)] : ""
                font.pixelSize: Theme.fsXs; color: Theme.textMuted
            }
            MouseArea { id: wma; anchors.fill: parent; hoverEnabled: true }
            Tip { visible: wma.containsMouse; text: modelData.tip; x: wma.mouseX + 12; y: wma.mouseY + 16 }
        }
    }
}
