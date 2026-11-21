import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Panoramica (G.1, in QML). Disegna soltanto `vm.snapshot` (testi, soglie e colori-gravità arrivano già decisi da Python).
Rectangle {
    id: root
    color: Theme.bg
    property var d: vm.snapshot

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight + Theme.sp4 + Theme.sp6
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            contentItem: Rectangle { implicitWidth: 6; radius: 3; color: Theme.borderStrong; opacity: parent.active || parent.hovered ? 1 : 0.55 }
            background: Item {}
        }

        ColumnLayout {
            id: page
            x: Theme.sp5; y: Theme.sp4
            width: flick.width - 2 * Theme.sp5 - 8
            spacing: Theme.sp4

            RowLayout {
                Layout.fillWidth: true
                Txt { text: "Panoramica"; font.pixelSize: Theme.fsXl; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                StatusPill { level: d.pill.level; label: d.pill.text }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sp4
                Repeater {
                    model: 4
                    KpiCard {
                        Layout.fillWidth: true; Layout.preferredWidth: 100
                        info: d.kpis[index]
                        order: index
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sp4
                Card {
                    Layout.fillWidth: true; Layout.preferredWidth: 600; Layout.fillHeight: true
                    title: "Forma e fatica della rosa"; hint: "ultime " + d.trend.weeks + " settimane"; order: 4
                    TrendChart {
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 200
                        form: d.trend.form; fatigue: d.trend.fatigue; tips: d.trend.tips; emptyText: d.trend.emptyText
                    }
                }
                Card {
                    Layout.fillWidth: true; Layout.preferredWidth: 400; Layout.fillHeight: true
                    title: "Priorità della settimana"; order: 5
                    Repeater {
                        model: d.actions
                        ActionRow { Layout.fillWidth: true; info: modelData }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sp4
                Card {
                    Layout.fillWidth: true; Layout.preferredWidth: 600; Layout.fillHeight: true
                    title: "Stagione"; order: 6
                    Txt { Layout.fillWidth: true; text: d.season.lead; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
                    SeasonTimeline {
                        Layout.fillWidth: true; Layout.preferredHeight: 84
                        visible: d.season.showTimeline
                        weeks: d.season.weeks; phases: d.season.phases
                    }
                    ProgressBar2 { Layout.fillWidth: true; value: d.season.progress.value; maximum: d.season.progress.max; label: d.season.progress.text }
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Txt { Layout.fillWidth: true; text: d.season.records; font.pixelSize: Theme.fsSm; color: Theme.textMuted; wrapMode: Text.WordWrap }
                            Txt { Layout.fillWidth: true; visible: d.season.contracts !== ""; text: d.season.contracts; font.pixelSize: Theme.fsSm; color: Theme.textMuted; wrapMode: Text.WordWrap }
                        }
                        PillButton { text: "Albo & Record →"; onClicked: vm.navigate(8) }
                    }
                }
                Card {
                    Layout.fillWidth: true; Layout.preferredWidth: 400; Layout.fillHeight: true
                    title: "Obiettivi di stagione"; order: 7
                    Repeater {
                        model: d.objectives
                        ObjectiveRow { Layout.fillWidth: true; info: modelData }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sp4
                Card {
                    Layout.fillWidth: true; Layout.preferredWidth: 600; Layout.fillHeight: true
                    title: "Dove sono forti e deboli"; hint: "punteggio atteso per gara, oggi"; order: 8
                    HeatMap { Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; Layout.alignment: Qt.AlignTop; heat: d.heat }
                    Item { Layout.fillHeight: true }
                }
                Card {
                    Layout.fillWidth: true; Layout.preferredWidth: 400; Layout.fillHeight: true
                    title: "Momenti memorabili & cronaca"; order: 9
                    Repeater {
                        model: d.news
                        Txt {
                            Layout.fillWidth: true
                            text: modelData.text; wrapMode: Text.WordWrap
                            font.pixelSize: Theme.fsSm + 1
                            color: modelData.star ? Theme.warn : Theme.text
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            Card {
                Layout.fillWidth: true
                title: "Migliori atleti in rosa"; hint: "doppio clic per la Scheda Atleta"; order: 10
                TopTable { Layout.fillWidth: true; table: d.top }
            }
        }
    }
}
