# Implementation Plan: blink1-tool-commands

## Overview

Ce plan décompose l'implémentation en étapes incrémentales : d'abord le module de commandes pur (builders, parsers, validators), puis l'extension du transport avec la lecture HID, le parsing de chaînes de patterns, l'enregistrement des services HA, et enfin les gestionnaires asynchrones (ServerTickleManager, BlinkEffectManager). Les tests property-based et unitaires accompagnent chaque composant.

## Tasks

- [x] 1. Module commands.py — Constantes, dataclasses et fonctions de validation
  - [x] 1.1 Créer le fichier `custom_components/blink1_status/commands.py` avec les constantes du protocole, les dataclasses de résultat (RGBColor, PatternLine, PlayState) et les fonctions de validation (validate_rgb, validate_led_index, validate_position, validate_fade_ms)
    - Définir les constantes : REPORT_ID, CMD_SET_RGB_NOW, CMD_FADE_TO_RGB, CMD_READ_COLOR, CMD_GET_VERSION, CMD_SET_PATTERN_LINE, CMD_READ_PATTERN_LINE, CMD_SAVE_PATTERNS, CMD_PLAY_LOOP, CMD_PLAY_STATE, CMD_SERVER_TICKLE, MAX_PATTERN_POS, MAX_LED_INDEX, MAX_FADE_MS, MAX_RGB
    - Implémenter les dataclasses frozen avec slots : RGBColor, PatternLine, PlayState
    - Implémenter les validateurs qui lèvent ValueError avec messages descriptifs
    - _Requirements: 1.3, 1.4, 4.2, 4.3, 5.2, 5.3, 5.4, 9.3, 9.4_

  - [ ]* 1.2 Écrire les tests property-based pour les fonctions de validation
    - **Property 6: Rejet des valeurs RGB hors bornes**
    - **Property 7: Rejet des LED_Index invalides**
    - **Property 8: Rejet des positions hors bornes**
    - **Property 9: Rejet des fade_ms hors bornes**
    - **Validates: Requirements 1.3, 1.4, 4.3, 5.2, 5.3, 5.4**

- [x] 2. Module commands.py — Builders de commandes d'écriture
  - [x] 2.1 Implémenter les builders d'écriture dans `commands.py` : build_set_rgb_now, build_fade_to_rgb, build_set_pattern_line, build_save_patterns, build_play_loop, build_stop_play, build_server_tickle_enable, build_server_tickle_disable
    - Chaque builder valide ses entrées avant de construire le rapport de 9 octets
    - Respecter le format exact du Feature_Report pour chaque commande
    - Encoder le fade_time en big-endian (th, tl) après division par 10
    - _Requirements: 1.1, 1.2, 5.1, 7.1, 9.1, 9.2, 11.1, 11.2_

  - [ ]* 2.2 Écrire les tests property-based pour les builders d'écriture
    - **Property 3: Structure de la commande Set RGB Now**
    - **Property 4: Structure de la commande Play Loop**
    - **Property 5: Structure et encodage de la commande Server Tickle Enable**
    - **Property 10: Rejet quand start >= end**
    - **Property 11: Rejet des timeout hors bornes pour Server Tickle**
    - **Validates: Requirements 1.1, 4.1, 9.1, 9.3, 11.1, 11.4, 11.5**

  - [ ]* 2.3 Écrire les tests unitaires pour les builders à sortie fixe
    - Tester build_save_patterns produit le rapport attendu avec commande 'W' (0x57)
    - Tester build_stop_play produit le rapport attendu avec play=0
    - Tester build_server_tickle_disable produit le rapport attendu avec on=0
    - Tester les valeurs par défaut (led_n=0, count=0)
    - _Requirements: 7.1, 9.2, 11.2_

- [x] 3. Module commands.py — Builders de requêtes de lecture et parsers de réponses
  - [x] 3.1 Implémenter les builders de requêtes de lecture : build_read_color_request, build_get_version_request, build_read_pattern_line_request, build_play_state_request
    - Chaque builder construit le rapport de 9 octets avec la commande appropriée
    - _Requirements: 2.1, 3.1, 6.1, 10.1_

  - [x] 3.2 Implémenter les parsers de réponses : parse_read_color_response, parse_get_version_response, parse_read_pattern_line_response, parse_play_state_response
    - Vérifier le marqueur de commande dans la réponse avant parsing
    - Extraire les valeurs selon la structure documentée du protocole
    - Lever OSError si le marqueur est invalide
    - _Requirements: 2.2, 3.1, 3.3, 6.2, 10.2_

  - [ ]* 3.3 Écrire les tests property-based pour les parsers de réponses
    - **Property 2: Aller-retour des Pattern Lines (build/parse)**
    - **Property 12: Parsing correct de la réponse de couleur**
    - **Property 13: Parsing correct de la version firmware**
    - **Property 14: Parsing correct du Play State**
    - **Property 15: Rejet des réponses sans marqueur de version**
    - **Validates: Requirements 2.2, 3.1, 3.3, 5.1, 6.2, 10.2**

- [x] 4. Checkpoint — Vérifier que le module commands.py est complet
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Parsing et formatage de chaînes de patterns
  - [x] 5.1 Implémenter `parse_pattern_string` et `format_pattern_lines` dans `commands.py`
    - Parser chaque segment séparé par `;`, extraire les 4 composantes séparées par `,`
    - Valider chaque segment : exactement 4 valeurs numériques, RGB 0-255, fade_ms 0-655350
    - Rejeter les chaînes vides, avec plus de 32 segments, ou avec des segments malformés
    - Le formateur produit la représentation canonique sans espaces superflus
    - _Requirements: 18.1, 18.2, 18.4, 18.5, 18.6_

  - [ ]* 5.2 Écrire les tests property-based pour le parsing/formatage de patterns
    - **Property 1: Aller-retour des chaînes de pattern (Round-trip)**
    - **Property 17: Rejet des chaînes de pattern malformées**
    - **Validates: Requirements 18.3, 18.5**

- [x] 6. Extension du Transport — Support de lecture HID
  - [x] 6.1 Ajouter la méthode `read(report_id: int = 0x01) -> bytes` à la classe de base `Blink1Transport` et aux implémentations `LinuxHidrawTransport` (via ioctl HIDIOCGFEATURE) et `PyHidTransport` (via `get_feature_report`)
    - LinuxHidrawTransport : préparer un buffer de 9 octets avec report_id en byte 0, appeler `fcntl.ioctl(fd, HIDIOCGFEATURE(9), buffer)`
    - PyHidTransport : appeler `device.get_feature_report(report_id, 9)`
    - Lever TimeoutError après 1 seconde sans réponse
    - Lever OSError si la réponse contient moins de 8 octets
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_

  - [ ]* 6.2 Écrire les tests unitaires pour le support de lecture du transport
    - **Property 16: Rejet des réponses tronquées**
    - Tester le timeout avec un mock qui ne répond pas
    - Tester la propagation des erreurs I/O
    - **Validates: Requirements 17.4, 17.5**

- [x] 7. Checkpoint — Vérifier la couche transport et le module commands
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Enregistrement des services HA dans `__init__.py`
  - [x] 8.1 Restructurer `hass.data[DOMAIN][entry_id]` pour stocker un dictionnaire `{ "transport", "tickle_manager", "blink_manager" }` au lieu du transport seul, et adapter les accès existants dans `light.py`
    - Modifier `async_setup_entry` pour créer le dictionnaire de données
    - Adapter `light.py` pour accéder à `hass.data[DOMAIN][entry_id]["transport"]`
    - _Requirements: 15.5_

  - [x] 8.2 Définir les schémas voluptuous de validation pour tous les services et implémenter la fonction `_register_services(hass)` qui enregistre les 13 services dans le domaine `blink1_status`
    - Schémas : SCHEMA_SET_PATTERN_LINE, SCHEMA_GET_PATTERN_LINE, SCHEMA_WRITE_PATTERN, SCHEMA_READ_PATTERN, SCHEMA_PLAY_PATTERN, SCHEMA_BLINK, SCHEMA_ENABLE_SERVER_TICKLE
    - Enregistrer les services : set_pattern_line, get_pattern_line, save_pattern, clear_pattern, write_pattern, read_pattern, play_pattern, stop_pattern, play_state, blink, enable_server_tickle, disable_server_tickle, get_device_state
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 13.1, 13.2, 13.3, 14.1, 15.1, 15.2, 16.1_

  - [x] 8.3 Implémenter les handlers de services de patterns : `_handle_set_pattern_line`, `_handle_get_pattern_line`, `_handle_save_pattern`, `_handle_clear_pattern`, `_handle_write_pattern`, `_handle_read_pattern`
    - Utiliser les builders/parsers de `commands.py` pour construire et parser les rapports HID
    - Exécuter les opérations I/O via `hass.async_add_executor_job`
    - Convertir ValueError et OSError en HomeAssistantError
    - Pour clear_pattern : écrire 32 Pattern_Lines noir à fade_ms=0
    - _Requirements: 5.1, 6.1, 7.1, 8.1, 8.2, 8.3, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 18.1, 18.2_

  - [x] 8.4 Implémenter les handlers de services de play loop : `_handle_play_pattern`, `_handle_stop_pattern`, `_handle_play_state`
    - Utiliser build_play_loop, build_stop_play, build_play_state_request et parse_play_state_response
    - _Requirements: 9.1, 9.2, 10.1, 10.2, 13.1, 13.2, 13.3, 13.4_

  - [x] 8.5 Implémenter le handler `_handle_get_device_state` qui lit séquentiellement la version firmware, la couleur courante et l'état de lecture
    - Enchaîner les 3 lectures avec gestion des erreurs individuelles
    - Timeout global de 5 secondes pour l'ensemble des opérations
    - _Requirements: 16.1, 16.2, 16.3_

- [x] 9. Checkpoint — Vérifier l'enregistrement et les handlers de services
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. ServerTickleManager — Gestion du watchdog keepalive
  - [x] 10.1 Implémenter la classe `ServerTickleManager` dans `__init__.py` avec les méthodes `start(timeout_ms, start, end)` et `stop()`, la boucle keepalive asynchrone, et l'instancier dans `async_setup_entry`
    - La boucle envoie le rapport server_tickle_enable à un intervalle de 50% du timeout
    - `stop()` annule la tâche et envoie server_tickle_disable
    - Gestion propre de asyncio.CancelledError
    - _Requirements: 11.1, 11.2, 11.3, 15.3, 15.4, 15.6_

  - [x] 10.2 Implémenter les handlers `_handle_enable_server_tickle` et `_handle_disable_server_tickle` qui délèguent au ServerTickleManager
    - enable : appelle tickle_manager.start() avec les paramètres validés
    - disable : appelle tickle_manager.stop()
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [x] 10.3 Modifier `async_unload_entry` pour appeler `tickle_manager.stop()` avant la fermeture du transport
    - Encapsuler dans un try/except pour garantir la fermeture même si le dispositif est déconnecté
    - _Requirements: 15.5_

  - [ ]* 10.4 Écrire les tests unitaires et d'intégration pour le ServerTickleManager
    - Tester le cycle start/stop avec un transport mocké
    - Tester que le keepalive envoie à l'intervalle correct (50% du timeout)
    - Tester la réactivation (stop ancien + start nouveau)
    - Tester le cleanup lors du unload avec tickle actif
    - _Requirements: 11.3, 15.3, 15.4, 15.5, 15.6_

- [x] 11. BlinkEffectManager — Gestion du clignotement
  - [x] 11.1 Implémenter la classe `BlinkEffectManager` dans `__init__.py` avec la méthode `start_blink(r, g, b, count, fade_ms, led_n)` et la logique de sauvegarde/restauration des pattern lines 0 et 1
    - Sauvegarder les patterns aux positions 0 et 1 avant le clignotement
    - Écrire la couleur cible à la position 0 et noir à la position 1
    - Démarrer le play loop sur positions 0-2 avec le count demandé
    - Attendre la fin du clignotement puis restaurer les patterns originaux
    - Annuler tout clignotement en cours avant d'en démarrer un nouveau
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 11.2 Implémenter le handler `_handle_blink` qui délègue au BlinkEffectManager et instancier le manager dans `async_setup_entry`
    - _Requirements: 14.1, 14.5_

  - [ ]* 11.3 Écrire les tests unitaires et d'intégration pour le BlinkEffectManager
    - Tester la séquence complète de clignotement avec transport mocké
    - Tester la sauvegarde et restauration des pattern lines
    - Tester l'annulation d'un blink en cours par un nouveau blink
    - Tester la gestion d'erreur lors de la restauration
    - _Requirements: 14.2, 14.3, 14.4_

- [x] 12. Checkpoint — Vérifier les gestionnaires asynchrones
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Tests d'intégration des services HA
  - [ ]* 13.1 Écrire les tests d'intégration pour les services de patterns et play loop
    - Tester l'enregistrement de tous les services dans le domaine blink1_status
    - Tester les appels de service avec transport mocké (write + read)
    - Tester la validation des schémas voluptuous (rejet des paramètres hors bornes)
    - Tester la conversion des erreurs en HomeAssistantError
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 13.1, 13.2, 13.3, 13.4_

  - [ ]* 13.2 Écrire les tests d'intégration pour le service get_device_state
    - Tester la lecture séquentielle des 3 informations (version, couleur, play state)
    - Tester le comportement quand une lecture individuelle échoue
    - Tester le timeout global de 5 secondes
    - _Requirements: 16.1, 16.2, 16.3_

- [x] 14. Checkpoint final — Ensemble de la suite de tests
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Les tâches marquées avec `*` sont optionnelles et peuvent être omises pour un MVP plus rapide
- Chaque tâche référence les requirements spécifiques pour assurer la traçabilité
- Les checkpoints permettent la validation incrémentale du développement
- Les property tests utilisent la bibliothèque Hypothesis avec minimum 100 itérations par propriété
- Les tests unitaires valident les cas concrets et les edge cases
- Le module `commands.py` est entièrement pur (sans I/O) pour faciliter les tests isolés
- L'approche incrémentale garantit qu'aucun code n'est orphelin : chaque étape s'intègre aux précédentes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 3, "tasks": ["3.2", "5.1"] },
    { "id": 4, "tasks": ["3.3", "5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "8.1"] },
    { "id": 6, "tasks": ["8.2"] },
    { "id": 7, "tasks": ["8.3", "8.4", "8.5"] },
    { "id": 8, "tasks": ["10.1", "11.1"] },
    { "id": 9, "tasks": ["10.2", "10.3", "11.2"] },
    { "id": 10, "tasks": ["10.4", "11.3"] },
    { "id": 11, "tasks": ["13.1", "13.2"] }
  ]
}
```
