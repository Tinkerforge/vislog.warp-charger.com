# -*- coding: utf-8 -*-
"""Internationalization strings for vislog.warp-charger.com"""

SUPPORTED_LANGUAGES = ['de', 'en']
DEFAULT_LANGUAGE = 'de'

TRANSLATIONS = {
    'de': {
        # --- index page ---
        'page_title_index': 'WARP Charger Ladeprotokoll- und Debug-Report-Visualisierer',
        'upload_heading': 'WARP Charger Ladeprotokoll oder Debug-Report hochladen',
        'upload_hint': 'Klicken oder Datei hierher ziehen',

        # --- protocol config page ---
        'page_title_protocol_config': 'WARP Charger Protokoll-Visualisierer - Spalten ausw\u00e4hlen',
        'select_columns_heading': 'Spalten f\u00fcr Visualisierung ausw\u00e4hlen',
        'search_columns_placeholder': 'Spalten durchsuchen...',
        'select_all': 'Alle ausw\u00e4hlen',
        'deselect_all': 'Alle abw\u00e4hlen',
        'default_selection': 'Standard-Auswahl',
        'show_chart': 'Chart anzeigen',
        'copy_link': 'Link kopieren',
        'copied': 'Kopiert!',
        'shareable_link': 'Teilbarer Link:',
        'predefined_badge': 'Standard',
        'select_at_least_one': 'Bitte w\u00e4hlen Sie mindestens eine Spalte aus.',
        'columns_shown_filtered': '${visible} von ${total} Spalten angezeigt',
        'columns_available': '${total} Spalten verf\u00fcgbar',

        # --- protocol chart page ---
        'page_title_protocol': 'WARP Charger Protokoll-Visualisierer',
        'columns_shown': 'Angezeigte Spalten',
        'log_axis': 'Y-Achse logarithmisch',
        'reset_zoom': 'Zoom zur\u00fccksetzen',
        'reset_zoom_title': 'Zur urspr\u00fcnglichen Ansicht zur\u00fcckkehren',
        'change_columns': 'Spalten \u00e4ndern',
        'zoom_hint': 'Ziehen zum Zoomen | Strg + Ziehen zum Verschieben',
        'chart_title': 'Ladeprotokoll',

        # --- protocol tabs ---
        'tab_config_before': 'Konfiguration vor dem Ladeprotokoll',
        'tab_config_after': 'Konfiguration nach dem Ladeprotokoll',
        'tab_log_before': 'Log vor dem Ladeprotokoll',
        'tab_log_after': 'Log nach dem Ladeprotokoll',

        # --- report page ---
        'page_title_report': 'WARP Charger Debug-Report-Visualisierer',
        'tab_configuration': 'Konfiguration',
        'tab_event_log': 'Ereignis-Log',
        'tab_trace_log': 'Trace-Log',
        'tab_coredump': 'Coredump',
        'firmware_info': 'Firmware-Informationen',
        'firmware_label': 'Firmware:',
        'commit_label': 'Commit:',
        'crashed_task_handle': 'Crashed Task Handle:',
        'exception_cause': 'Ausnahmeursache',
        'code_label': 'Code:',
        'name_label': 'Name:',
        'description_label': 'Beschreibung:',
        'registers': 'Register',
        'register_col': 'Register',
        'value_col': 'Wert',
        'parsing_warning': 'Parsing-Warnung',
        'coredump_hint': 'F\u00fcr eine vollst\u00e4ndige Stack-Trace-Analyse mit GDB kann das',
        'coredump_hint_suffix': '-Skript aus dem esp32-firmware Repository verwendet werden.',
        'hint_label': 'Hinweis:',
        'no_coredump': 'Es befindet sich kein Coredump im Debug-Report.',

        # --- warnings ---
        'warning_label': 'Achtung:',
        'dropped_lines_warning': '${count} Zeilen wurden aus den CSV-Daten entfernt. Das Ladeprotokoll ist unvollst\u00e4ndig.',

        # --- common ---
        'toggle_theme': 'Dunkel-/Hellmodus umschalten',
        'switch_language': 'Switch to English',
        'lang_code': 'de',

        # --- JSON viewer (used in JS) ---
        'search_placeholder': 'Konfigurationen durchsuchen... (Enter: n\u00e4chster, Shift+Enter: vorheriger)',
        'filter_all': 'Alle',
        'filter_all_title': 'Alle Konfigurationen anzeigen',
        'filter_modified': 'Ge\u00e4ndert',
        'filter_modified_title': 'Nur ge\u00e4nderte Konfigurationen anzeigen',
        'filter_numbers': 'Zahlen',
        'filter_numbers_title': 'Nur numerische Werte anzeigen',
        'filter_strings': 'Texte',
        'filter_strings_title': 'Nur Textwerte anzeigen',
        'filter_booleans': 'Booleans',
        'filter_booleans_title': 'Nur boolesche Werte anzeigen',
        'filter_objects': 'Objekte',
        'filter_objects_title': 'Nur Objekt-/Array-Werte anzeigen',
        'expand_all': 'Alle aufklappen',
        'expand_all_title': 'Alle Knoten aufklappen',
        'collapse_all': 'Alle zuklappen',
        'collapse_all_title': 'Alle Knoten zuklappen',
        'legend_modified': 'Konfiguration ge\u00e4ndert',
        'legend_important': 'Konfiguration ge\u00e4ndert aber nicht gespeichert',
        'legend_info': 'API-Dokumentation verf\u00fcgbar',
        'matches': 'Treffer',
        'of': 'von',
        'popover_unit': 'Einheit',
        'popover_values': 'Werte:',

        # --- chart labels ---
        'chart_allowed_charging_current': 'Erlaubter Ladestrom (mA)',
        'chart_cp_pwm_duty_cycle': 'CP PWM (% Duty Cycle)',
        'chart_iec61851_state': 'IEC61851 State',
        'chart_power': 'Leistung (W)',
        'chart_current_0': 'Strom L1 (mA)',
        'chart_current_1': 'Strom L2 (mA)',
        'chart_current_2': 'Strom L3 (mA)',
        'chart_resistance_cp_pe': 'Widerstand CP/PE (Ohm)',
        'chart_contactor_state': 'Zustand Sch\u00fctz',
        'chart_contactor_error': 'Fehlerzustand Sch\u00fctz',
        'chart_phase_0_active': 'Phase 0 Aktiv',
        'chart_phase_1_active': 'Phase 1 Aktiv',
        'chart_phase_2_active': 'Phase 2 Aktiv',
        'chart_phase_0_connected': 'Phase 0 Verbunden',
        'chart_phase_1_connected': 'Phase 1 Verbunden',
        'chart_phase_2_connected': 'Phase 2 Verbunden',
        'chart_time_since_state_change': 'Zeit seit Zustandswechsel',
        'chart_voltage_plus_12v': 'Spannung +12V',
        'chart_voltage_minus_12v': 'Spannung -12V',
        'footer_ecosystem': 'Teil des WARP Charger Ökosystems',
        'footer_source': 'Quellcode auf GitHub',
    },
    'en': {
        # --- index page ---
        'page_title_index': 'WARP Charger Charge Log and Debug Report Visualizer',
        'upload_heading': 'Upload WARP Charger charge log or debug report',
        'upload_hint': 'Click or drag file here',

        # --- protocol config page ---
        'page_title_protocol_config': 'WARP Charger Protocol Visualizer - Select Columns',
        'select_columns_heading': 'Select columns for visualization',
        'search_columns_placeholder': 'Search columns...',
        'select_all': 'Select all',
        'deselect_all': 'Deselect all',
        'default_selection': 'Default selection',
        'show_chart': 'Show chart',
        'copy_link': 'Copy link',
        'copied': 'Copied!',
        'shareable_link': 'Shareable link:',
        'predefined_badge': 'Default',
        'select_at_least_one': 'Please select at least one column.',
        'columns_shown_filtered': '${visible} of ${total} columns shown',
        'columns_available': '${total} columns available',

        # --- protocol chart page ---
        'page_title_protocol': 'WARP Charger Protocol Visualizer',
        'columns_shown': 'Columns shown',
        'log_axis': 'Y-axis logarithmic',
        'reset_zoom': 'Reset zoom',
        'reset_zoom_title': 'Return to original view',
        'change_columns': 'Change columns',
        'zoom_hint': 'Drag to zoom | Ctrl + Drag to pan',
        'chart_title': 'Charge Log',

        # --- protocol tabs ---
        'tab_config_before': 'Configuration before charge log',
        'tab_config_after': 'Configuration after charge log',
        'tab_log_before': 'Log before charge log',
        'tab_log_after': 'Log after charge log',

        # --- report page ---
        'page_title_report': 'WARP Charger Debug Report Visualizer',
        'tab_configuration': 'Configuration',
        'tab_event_log': 'Event Log',
        'tab_trace_log': 'Trace Log',
        'tab_coredump': 'Coredump',
        'firmware_info': 'Firmware Information',
        'firmware_label': 'Firmware:',
        'commit_label': 'Commit:',
        'crashed_task_handle': 'Crashed Task Handle:',
        'exception_cause': 'Exception Cause',
        'code_label': 'Code:',
        'name_label': 'Name:',
        'description_label': 'Description:',
        'registers': 'Registers',
        'register_col': 'Register',
        'value_col': 'Value',
        'parsing_warning': 'Parsing Warning',
        'coredump_hint': 'For a complete stack trace analysis with GDB, use the',
        'coredump_hint_suffix': ' script from the esp32-firmware repository.',
        'hint_label': 'Note:',
        'no_coredump': 'No coredump found in the debug report.',

        # --- warnings ---
        'warning_label': 'Warning:',
        'dropped_lines_warning': '${count} lines were removed from the CSV data. The charge log is incomplete.',

        # --- common ---
        'toggle_theme': 'Toggle dark/light mode',
        'switch_language': 'Auf Deutsch wechseln',
        'lang_code': 'en',

        # --- JSON viewer (used in JS) ---
        'search_placeholder': 'Search configurations... (Enter: next, Shift+Enter: previous)',
        'filter_all': 'All',
        'filter_all_title': 'Show all configurations',
        'filter_modified': 'Modified',
        'filter_modified_title': 'Show only modified configurations',
        'filter_numbers': 'Numbers',
        'filter_numbers_title': 'Show only numeric values',
        'filter_strings': 'Strings',
        'filter_strings_title': 'Show only string values',
        'filter_booleans': 'Booleans',
        'filter_booleans_title': 'Show only boolean values',
        'filter_objects': 'Objects',
        'filter_objects_title': 'Show only object/array values',
        'expand_all': 'Expand all',
        'expand_all_title': 'Expand all nodes',
        'collapse_all': 'Collapse all',
        'collapse_all_title': 'Collapse all nodes',
        'legend_modified': 'Configuration modified',
        'legend_important': 'Configuration modified but not saved',
        'legend_info': 'API documentation available',
        'matches': 'matches',
        'of': 'of',
        'popover_unit': 'Unit',
        'popover_values': 'Values:',

        # --- chart labels ---
        'chart_allowed_charging_current': 'Allowed charging current (mA)',
        'chart_cp_pwm_duty_cycle': 'CP PWM (% Duty Cycle)',
        'chart_iec61851_state': 'IEC61851 State',
        'chart_power': 'Power (W)',
        'chart_current_0': 'Current L1 (mA)',
        'chart_current_1': 'Current L2 (mA)',
        'chart_current_2': 'Current L3 (mA)',
        'chart_resistance_cp_pe': 'Resistance CP/PE (Ohm)',
        'chart_contactor_state': 'Contactor state',
        'chart_contactor_error': 'Contactor error state',
        'chart_phase_0_active': 'Phase 0 active',
        'chart_phase_1_active': 'Phase 1 active',
        'chart_phase_2_active': 'Phase 2 active',
        'chart_phase_0_connected': 'Phase 0 connected',
        'chart_phase_1_connected': 'Phase 1 connected',
        'chart_phase_2_connected': 'Phase 2 connected',
        'chart_time_since_state_change': 'Time since state change',
        'chart_voltage_plus_12v': 'Voltage +12V',
        'chart_voltage_minus_12v': 'Voltage -12V',
        'footer_ecosystem': 'Part of the WARP Charger ecosystem',
        'footer_source': 'Source on GitHub',
    },
}


def get_translations(lang):
    """Return the translation dict for the given language code."""
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    return TRANSLATIONS[lang]
