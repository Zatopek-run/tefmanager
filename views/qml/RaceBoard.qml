import QtQuick
import QtQuick.Layouts

// Tabellone live della gara in pista (G.3): classifica che si riordina, velocità e distacchi. Disegna solo `vm.board` (sola lettura).
Rectangle {
    id: root
    color: Theme.surface
    radius: Theme.radiusLg
    border.width: 1
    border.color: Theme.border

    property var b: vm.board
    property string currentRace: ""
    readonly property int rowH: 46

    ListModel { id: model }

    // Le righe restano nell'ordine dei corridori (identità stabile): cambia solo `rank`, e la riga scorre al suo posto.
    function sync() {
        var rows = b.rows || []
        if (b.raceId !== currentRace || model.count !== rows.length) {
            model.clear()
            currentRace = b.raceId
            for (var i = 0; i < rows.length; i++) model.append(rows[i])
        } else {
            for (var j = 0; j < rows.length; j++) model.set(j, rows[j])
        }
    }
    onBChanged: sync()

    ColumnLayout {
        anchors { fill: parent; margins: Theme.sp3 }
        spacing: Theme.sp2

        RowLayout {
            Layout.fillWidth: true
            Txt { text: "TABELLONE LIVE"; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold; font.letterSpacing: 0.8; color: Theme.textMuted }
            Item { Layout.fillWidth: true }
            Rectangle {
                visible: root.b.phase !== "" || root.b.replay || root.b.done
                implicitHeight: 20; implicitWidth: tag.implicitWidth + 16; radius: 10
                color: root.b.replay ? Qt.rgba(0.38, 0.65, 0.98, 0.18) : root.b.done ? Qt.rgba(0.2, 0.83, 0.6, 0.16) : Qt.rgba(0.98, 0.75, 0.14, 0.16)
                Txt { id: tag; anchors.centerIn: parent; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold
                      text: root.b.replay ? "REPLAY" : root.b.done ? "ARRIVATA" : root.b.phase
                      color: root.b.replay ? Theme.info : root.b.done ? Theme.good : Theme.warn }
            }
        }

        Txt { text: root.b.clock || "0.00s"; font.pixelSize: 30; font.weight: Font.Bold }

        RowLayout {
            Layout.fillWidth: true; spacing: Theme.sp4
            ColumnLayout { spacing: 0
                Txt { text: "PASSO DEL PRIMO"; font.pixelSize: Theme.fsXs; color: Theme.textFaint; font.letterSpacing: 0.5 }
                Txt { text: root.b.started && !root.b.done ? root.b.leaderKmh.toFixed(1) + " km/h" : "—"; font.weight: Font.DemiBold } }
            ColumnLayout { spacing: 0
                Txt { text: "DISTACCO 1°–2°"; font.pixelSize: Theme.fsXs; color: Theme.textFaint; font.letterSpacing: 0.5 }
                Txt { text: root.b.firstSecond !== "" ? root.b.firstSecond : "—"; font.weight: Font.DemiBold } }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: model.count * root.rowH
            Repeater {
                model: model
                delegate: Item {
                    id: row
                    width: parent.width; height: root.rowH - 6
                    y: (rank - 1) * root.rowH
                    Behavior on y { NumberAnimation { duration: 380 * Theme.animScale; easing.type: Easing.OutCubic } }
                    readonly property color kitColor: kit

                    Rectangle {   // sfondo: il giocatore in evidenza
                        anchors.fill: parent; radius: Theme.radiusMd
                        color: isPlayer ? Qt.rgba(0.1, 0.83, 0.75, 0.12) : Theme.surface2
                        border.width: isPlayer ? 1 : 0; border.color: Theme.accentDim
                    }
                    Rectangle { x: 0; y: 6; width: 3; height: parent.height - 12; radius: 1.5; color: row.kitColor }

                    Rectangle {   // posto
                        x: 12; y: 8; width: 24; height: 24; radius: 12
                        color: rank === 1 ? Theme.accent : Theme.bg
                        border.width: 1; border.color: rank === 1 ? Theme.accent : Theme.borderStrong
                        Txt { anchors.centerIn: parent; text: rank; font.pixelSize: Theme.fsSm; font.weight: Font.Bold; color: rank === 1 ? Theme.bg : Theme.text }
                    }
                    Txt { x: 44; y: 2; width: row.width - 44 - 74; elide: Text.ElideRight; text: name
                          font.weight: isPlayer ? Font.Bold : Font.DemiBold; font.pixelSize: Theme.fsMd }
                    Txt { x: 44; y: 19; width: row.width - 44 - 74; elide: Text.ElideRight; font.pixelSize: Theme.fsXs; color: Theme.textMuted
                          text: (bib > 0 ? "#" + bib + " · " : "") + team }
                    Txt { y: 2; anchors.right: parent.right; anchors.rightMargin: 10; horizontalAlignment: Text.AlignRight
                          text: finished ? markText : gap; font.weight: Font.Bold; font.pixelSize: Theme.fsSm + 1
                          color: dnf ? Theme.bad : (finished ? Theme.good : Theme.text) }
                    Txt { y: 19; anchors.right: parent.right; anchors.rightMargin: 10; horizontalAlignment: Text.AlignRight
                          text: finished ? (rank > 1 && gap !== "" ? gap : "") : (dnf ? "" : speedKmh.toFixed(1) + " km/h")
                          font.pixelSize: Theme.fsXs; color: Theme.textMuted }
                    Rectangle {   // avanzamento sulla distanza
                        x: 44; y: parent.height - 7; width: row.width - 44 - 10; height: 3; radius: 1.5; color: Theme.bg
                        Rectangle { height: parent.height; radius: 1.5; color: dnf ? Theme.bad : row.kitColor
                                    width: parent.width * Math.max(0, Math.min(1, pct))
                                    Behavior on width { NumberAnimation { duration: 90 * Theme.animScale } } }
                    }
                }
            }
        }
    }
}
