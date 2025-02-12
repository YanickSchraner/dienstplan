# Anforderungskatalog für die automatisierte Dienstplanerstellung

## 1. Einleitung

Dieses Dokument beschreibt die Anforderungen an eine Software zur automatisierten Dienstplanerstellung für ein Altenheim. Das Ziel ist es, die Dienstplanung zu automatisieren und gleichzeitig die individuellen Bedürfnisse der Mitarbeiter und die gesetzlichen Vorgaben zu berücksichtigen.

## 2. Funktionen

Die Software soll folgende Funktionen bieten:

*   **Import von Mitarbeiterdaten:** Die Mitarbeiterdaten (Name, Qualifikation, Arbeitszeitmodell, Verfügbarkeit, etc.) sollen aus einer Excel-Tabelle importiert werden können. Die Excel-Tabelle hat folgendes Format:

| Name | Diensttage | Qualifikation | SL | W | Fe | UW |
|---|---|---|---|---|---|---|
| ZE | 20 | Leitung |  | 21.2. |  |  |
| DR | 16 | HF |  |  |  |  |
| MM | 16 | HF |  |  |  |  |
| CV | 16 | HF |  | 24.2. |  |  |
| FM | 10 | HF |  | 7.2., 17.2., 8.2.,9.2.,15.2.,16.2. | 10.2.-14.2. |  |
| KL | 20 | Ausbildung 2 | 5.2., 12.2., 19.2., 26.2. |  |  |  |
| KJ | 16 | Ausbildung 2 |  |  |  | 7.2., 12.2, 14.2., 21.2., 28.2. |
| GN | 14 | PH |  | 24.2. | 8.2.-23.2. |  |
| RG | 16 | PH |  | 1.2.,2.2. |  |  |
| GN2 | 20 | PH |  |  |  |  |
| BK | 16 | PH |  | 21.2., 22.2. |  |  |
| ND | 16 | PH |  | 7.2.,13.2.,20.2., 27.2. |  |  |
| BN | 14 | PH |  | 7.2., 17.2. | 8.2. - 16.2. |  |
| HM | 10 | PH |  |  |  |  |
| BS | 16 | PH |  | 24.2. | 15.2. - 23.2. |  |
| BT | 16 | PH |  |  |  |  |
| SC | 10 | PH |  | 7.2., 14.2., 21.2., 28.2. |  |  |
| MT | 16 | PH |  |  |  |  |
| TM | 20 | Ausbildung 1 | 3.2., 4.2., 10.2.,11.2.,17.2.,18.2.,21.2.,24.2.25.2.,28.2. |  |  |  |

*   **Automatische Dienstplanerstellung:** Die Software soll Dienstpläne unter Berücksichtigung der Mitarbeiterdaten, der Schichtarten und der definierten Regeln automatisch erstellen.
*   **Manuelle Anpassung:** Die Software soll es ermöglichen, die automatisch erstellten Dienstpläne manuell anzupassen.
*   **Export der Dienstpläne:** Die Dienstpläne sollen in eine Excel-Tabelle exportiert werden können.

## 3. Daten

Die Software soll folgende Daten verarbeiten können:

**Mitarbeiterdaten:**

*   Name
*   Qualifikation (Leitung, HF, PH, Ausbildung)
*   Arbeitspensum (in Prozent)
*   In Ausbildung (ja/nein)
*   Wunschfrei
*   Weiterbildungen
*   Krankheitsausfälle
*   Ferien

**Schichtarten:**

*   **Frühdienste:**
    *   B Dienst: 6:45 Uhr - 16:00 Uhr
    *   C Dienst: 7:30 Uhr - 16:45 Uhr
*   **Spätdienste:**
    *   VS Dienst: 11:00 Uhr - 20:15 Uhr
    *   S Dienst: 12:00 Uhr - 21:15 Uhr
*   **Geteilte Dienste:**
    *   BS Dienst: 6:45 Uhr - 11:00 Uhr und 17:00 Uhr - 21:15 Uhr
    *   C4 Dienst: 7:30 Uhr - 12:30 Uhr und 16:45 Uhr - 20:09 Uhr
*   **Bürodienst (nur für Leitung):** Bü Dienst

**Abwesenheiten:**

*   Wunschfrei (.w)
*   Frei (.x)
*   Ferien (Fe)
*   Weiterbildung (IW)
*   Schule (SL)
*   Unbezahlte Schule (uw)
*   Krankheit (Kr)

## 4. Regeln

Bei der automatischen Dienstplanerstellung sollen folgende Regeln berücksichtigt werden:

*   **Vordefinierte Dienste:** Schule (SL), unbezahlte Schule (uw), Wunschfrei (.w), Ferien (Fe) und Krankheiten (Kr) sind vor dem Planen bereits bekannt und müssen berücksichtigt werden.
*   **Lehrlinge:**
    *   Lehrlinge mit der Qualifikation "Ausbildung 1" dürfen nur unter der Woche arbeiten und ausschliesslich einen B oder C Dienst machen.
    *   Lehrlinge mit der Qualifikation "Ausbildung 2" dürfen maximal 1 Wochenende pro Monat machen. Zudem dürfen sie auch Spätdienste durchführen. Sie dürfen nur einmal pro Monat an einem Sonntag oder Feiertag arbeiten.
*   **Wochenenden:** Generell sollten nicht mehr als 2 Wochenenden pro Person geplant werden.
*   **Leitung:** Die Leitung arbeitet generell nur unter der Woche und muss pro Monat 4 Bürotage (Bü Dienst) geplant haben.
*   **Qualifikation pro Schicht:**
    *   **Frühschicht:**
        *   Minimum 1 Fachperson (HF/Leitung) und 4 nicht Fachpersonen (PH/Ausbildung).
        *   Maximum 2 Fachpersonen und 6 nicht Fachpersonen.
        *   Eine Fachperson im B Dienst.
        *   Minimum 3 Personen im B Dienst (eine Fachperson und 2 Helfer).
        *   Total also 5 - 8 Personen im Frühdienst.
    *   **Spätschicht:**
        *   Minimum 1 Fachperson und 2 nicht Fachpersonen.
        *   Maximum 1 Fachperson und 3 nicht Fachpersonen.
        *   Eine Fachperson im S Dienst.
        *   Maximum eine Person im VS Dienst.
        *   Total also 3-4 Mitarbeiter in der Spätschicht.
    *   **Geteilte Schicht:**
        *   Maximal 3 geteilte Dienste (C4 und BS) an einem Tag.
        *   Die Anzahl an geteilten Schichten soll möglichst gering sein.
        *   Eine Person in einer geteilten Schicht zählt sowohl als geplant in der Frühschicht als auch in der Spätschicht.
*   **Frei haben:** Mitarbeiter dürfen frei haben. Dies wird mit "x" eingetragen.
*   **Fachpersonen:** HF und Leitung
*   **Nicht Fachpersonen:** Ausbildung und PH
*   **Leitung:** Hat bis zu 4 Bürotage im Monat. Arbeitet nicht am Wochenende. Hat sonst B Dienste unter der Woche.
*   **Aufeinanderfolgende Dienste:** Eine Person darf nicht mehr als 5 aufeinanderfolgende Dienste haben.
*   **Wechsel von Spät- auf Frühdienst:** Ein Wechsel von Spätdienst auf Frühdienst ist nur in folgenden Kombinationen erlaubt: VS auf C und C4 auf C.
*   **Ziel Diensttage:** Eine Person hat eine Anzahl an Diensttagen pro Monat (target wordays). Diese soll als Zielwert für die Anzahl Schichten pro Monat dienen. Als Diensttag zählen Schichten, SL und Ferientage. Es ist ok, wenn eine Person weniger als die Ziel Diensttage in einem Monat arbeitet.
*   **Büro Schicht:** Die Büro Schicht zählt nicht als Früh- oder Spätdienst. Dieser Dienst darf der Anzahl an Personen im Frühdienst oder Spätdienst nicht angerechnet werden.

## Software

Ich verwende Python 3.12 und die Bibliotheken:
* Streamlit
* HiGHS (https://ergo-code.github.io/HiGHS/dev/executable/)
