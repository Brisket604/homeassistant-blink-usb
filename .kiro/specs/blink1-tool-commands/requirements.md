# Requirements Document

## Introduction

Cette fonctionnalité étend l'intégration Home Assistant blink(1) USB pour prendre en charge l'ensemble des commandes HID du protocole blink(1), équivalentes à celles offertes par l'outil CLI `blink1-tool`. L'objectif est d'exposer la gestion des patterns de couleurs, les effets visuels, le ciblage de LEDs individuelles, le watchdog (server tickle) et la lecture de l'état du dispositif sous forme de services Home Assistant.

## Glossary

- **Transport**: Couche d'abstraction pour la communication HID avec le périphérique blink(1)
- **Pattern_Line**: Une entrée dans la mémoire de patterns du blink(1), composée d'une couleur RGB et d'un temps de fondu, stockée à une position donnée (0-31)
- **Pattern**: Séquence ordonnée de Pattern_Lines définissant une animation de couleurs
- **Play_Loop**: Lecture en boucle d'un sous-ensemble de Pattern_Lines entre une position de début et une position de fin
- **Server_Tickle**: Mécanisme watchdog du blink(1) qui joue automatiquement un pattern si l'hôte cesse de communiquer dans un délai configuré
- **LED_Index**: Identifiant de la LED cible (0 = toutes, 1 = LED supérieure, 2 = LED inférieure sur les modèles mk2+)
- **Feature_Report**: Rapport HID de 9 octets utilisé pour communiquer avec le blink(1)
- **Service_HA**: Service Home Assistant enregistré dans le domaine de l'intégration, appelable via l'interface ou les automatisations
- **Blink1_Device**: Instance du transport HID ouverte vers un périphérique blink(1) physique
- **Fade_Time**: Durée de transition en millisecondes entre la couleur actuelle et la couleur cible

## Requirements

### Requirement 1: Commande Set RGB instantané

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir définir une couleur RGB instantanément (sans fondu), afin de changer rapidement l'état visuel de la LED.

#### Acceptance Criteria

1. WHEN une couleur RGB (r, g, b chacun dans l'intervalle 0-255) et un LED_Index (0, 1 ou 2) sont fournis, THE Transport SHALL envoyer un Feature_Report de 9 octets au format { 0x01, 0x6E, r, g, b, 0x00, 0x00, led_n, 0x00 }
2. WHEN le LED_Index est omis, THE Transport SHALL utiliser la valeur 0 (toutes les LEDs) comme LED_Index dans le Feature_Report
3. IF une ou plusieurs valeurs RGB sont hors de l'intervalle 0-255 (inférieures à 0 ou supérieures à 255), THEN THE Transport SHALL rejeter la commande sans envoyer de Feature_Report et lever une exception ValueError indiquant quelles valeurs sont hors limites
4. IF le LED_Index fourni est en dehors de l'intervalle 0-2, THEN THE Transport SHALL rejeter la commande sans envoyer de Feature_Report et lever une exception ValueError indiquant la valeur invalide de LED_Index

### Requirement 2: Lecture de la couleur courante

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir lire la couleur actuellement affichée par une LED, afin de synchroniser l'état de l'interface avec le périphérique.

#### Acceptance Criteria

1. WHEN une lecture de couleur est demandée pour un LED_Index donné, THE Transport SHALL envoyer un Feature_Report de 9 octets avec la commande 'r' (0x72) et le LED_Index au byte 7, puis lire la réponse du périphérique dans un délai maximal de 1 seconde
2. WHEN la réponse est reçue, THE Transport SHALL extraire les octets rouge, vert et bleu de la réponse et retourner un tuple (r, g, b) avec chaque valeur comprise entre 0 et 255
3. IF la lecture échoue en raison d'une erreur de communication, THEN THE Transport SHALL lever une exception OSError avec un message indiquant la nature de l'échec
4. WHEN le LED_Index est omis, THE Transport SHALL utiliser la valeur 0 (toutes les LEDs)
5. IF un LED_Index supérieur à 2 est fourni, THEN THE Transport SHALL rejeter la commande avec une erreur indiquant que la valeur doit être 0, 1 ou 2

### Requirement 3: Lecture de la version du firmware

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir lire la version du firmware du blink(1), afin de diagnostiquer la compatibilité et d'afficher cette information dans le registre des périphériques.

#### Acceptance Criteria

1. WHEN une lecture de version est demandée, THE Transport SHALL envoyer un Feature_Report avec la commande 'v' (0x76) et retourner la version sous forme de chaîne composée de la valeur décimale de l'octet major, suivie d'un point, suivie de la valeur décimale de l'octet minor (exemple : octets 0x02 et 0x0A produisent "2.10")
2. IF la lecture échoue en raison d'une erreur de communication ou d'un timeout, THEN THE Transport SHALL lever une exception OSError avec un message indiquant la cause de l'échec (erreur I/O ou absence de réponse)
3. IF la réponse reçue ne contient pas le marqueur de commande 'v' (0x76) à la position attendue, THEN THE Transport SHALL lever une exception OSError avec un message indiquant une réponse invalide du périphérique

### Requirement 4: Ciblage de LED individuelle

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir cibler une LED spécifique sur les dispositifs blink(1) mk2+, afin de contrôler chaque LED indépendamment.

#### Acceptance Criteria

1. WHEN un LED_Index est fourni aux commandes fade_to_rgb, set_rgb_now et read_color, THE Transport SHALL inclure cet index dans le Feature_Report au byte 7
2. THE Transport SHALL accepter les valeurs de LED_Index 0 (toutes), 1 (supérieure) et 2 (inférieure)
3. IF un LED_Index inférieur à 0 ou supérieur à 2 est fourni, THEN THE Transport SHALL rejeter la commande avec une erreur indiquant la valeur reçue et l'intervalle valide (0-2)
4. WHEN le LED_Index est omis, THE Transport SHALL utiliser la valeur par défaut 0 (toutes les LEDs)

### Requirement 5: Écriture d'une ligne de pattern

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir écrire une entrée de pattern (couleur + temps de fondu) à une position donnée en mémoire RAM du blink(1), afin de composer des animations personnalisées.

#### Acceptance Criteria

1. WHEN une couleur RGB (chaque composante dans 0-255), un Fade_Time (0-655350ms) et une position (0-31) sont fournis, THE Transport SHALL envoyer un Feature_Report de 9 octets au format { 0x01, 0x50, r, g, b, th, tl, pos, 0x00 } où th et tl encodent le fade time arrondi à la dizaine inférieure divisé par 10 en big-endian
2. IF la position est hors de l'intervalle 0-31, THEN THE Transport SHALL rejeter la commande avec une ValueError indiquant la position invalide et l'intervalle attendu (0-31)
3. IF le Fade_Time est négatif ou supérieur à 655350ms, THEN THE Transport SHALL rejeter la commande avec une ValueError indiquant les bornes acceptables (0-655350ms)
4. IF une ou plusieurs valeurs RGB sont hors de l'intervalle 0-255, THEN THE Transport SHALL rejeter la commande avec une ValueError indiquant quelles valeurs sont invalides

### Requirement 6: Lecture d'une ligne de pattern

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir lire une entrée de pattern stockée à une position donnée, afin de vérifier le contenu actuel de la mémoire de patterns.

#### Acceptance Criteria

1. WHEN une position (0-31) est fournie, THE Transport SHALL envoyer un Feature_Report avec la commande 'R' (0x52) et la position, puis lire la réponse du périphérique
2. WHEN la réponse est reçue, THE Transport SHALL retourner un tuple (r, g, b, fade_ms) où r, g, b sont compris entre 0 et 255 et fade_ms est reconstruit à partir des octets th et tl de la réponse selon la formule (th * 256 + tl) * 10, produisant une valeur entre 0 et 655350 millisecondes
3. IF la position est hors de l'intervalle 0-31, THEN THE Transport SHALL rejeter la commande avec une ValueError indiquant la position invalide et l'intervalle attendu
4. IF la lecture échoue en raison d'une erreur de communication, THEN THE Transport SHALL lever une exception OSError avec un message descriptif

### Requirement 7: Sauvegarde des patterns en mémoire flash

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir sauvegarder les patterns de la RAM vers la mémoire flash du blink(1), afin de les conserver après une coupure d'alimentation.

#### Acceptance Criteria

1. WHEN une sauvegarde est demandée, THE Transport SHALL envoyer un Feature_Report de 9 octets avec le report ID 0x01, la commande 'W' (0x57), et les octets restants à 0x00, provoquant l'écriture des 32 Pattern_Lines de la RAM vers la mémoire flash
2. IF l'écriture échoue en raison d'une erreur de communication HID, THEN THE Transport SHALL lever une exception OSError avec un message indiquant l'échec de la sauvegarde
3. IF le dispositif ne supporte pas la sauvegarde flash (modèle antérieur au mk2), THEN THE Transport SHALL lever une exception avec un message indiquant l'incompatibilité du dispositif

### Requirement 8: Effacement des patterns

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir effacer toutes les lignes de pattern (mettre à noir avec un fade de 0ms), afin de réinitialiser la mémoire de patterns.

#### Acceptance Criteria

1. WHEN un effacement est demandé, THE Transport SHALL écrire une Pattern_Line (0, 0, 0, 0ms) à chacune des 32 positions dans l'ordre croissant (0 à 31) en mémoire RAM uniquement, sans déclencher de sauvegarde en flash
2. WHEN l'effacement est terminé, THE Transport SHALL avoir envoyé exactement 32 Feature_Reports de commande 'P' (0x50)
3. IF une erreur de communication survient lors de l'écriture d'une position pendant l'effacement, THEN THE Transport SHALL interrompre l'opération et lever une exception OSError indiquant la position à laquelle l'écriture a échoué

### Requirement 9: Lecture et contrôle du Play Loop

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir démarrer et arrêter la lecture en boucle des patterns stockés, afin d'animer la LED sans intervention continue de l'hôte.

#### Acceptance Criteria

1. WHEN un démarrage de Play_Loop est demandé avec une position de début (0–31), une position de fin (0–31) et un nombre de répétitions (0–255, où 0 signifie boucle infinie), THE Transport SHALL envoyer un Feature_Report de 9 octets avec la structure {0x01, 0x70, 0x01, start_pos, end_pos, count, 0x00, 0x00, 0x00}
2. WHEN un arrêt de Play_Loop est demandé, THE Transport SHALL envoyer un Feature_Report de 9 octets avec la structure {0x01, 0x70, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
3. IF la position de début est supérieure ou égale à la position de fin, THEN THE Transport SHALL rejeter la commande en levant une exception ValueError indiquant les positions invalides sans envoyer de Feature_Report
4. IF la position de début ou la position de fin est en dehors de l'intervalle 0–31, THEN THE Transport SHALL rejeter la commande en levant une exception ValueError indiquant la position hors limites sans envoyer de Feature_Report

### Requirement 10: Lecture de l'état de lecture (Play State)

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir lire l'état actuel de lecture des patterns, afin de savoir si un pattern est en cours de lecture et à quelle position.

#### Acceptance Criteria

1. WHEN une lecture du Play State est demandée, THE Transport SHALL envoyer un Feature_Report de 8 octets { 0x01, 0x53, 0, 0, 0, 0, 0, 0 } au périphérique et lire la réponse dans un délai maximum de 1000 ms
2. WHEN la réponse de 8 octets est reçue, THE Transport SHALL retourner un objet contenant : playing (bool, octet 2 : 0=arrêté, 1=en lecture), position_début (int, octet 3, valeur de 0 à 31), position_fin (int, octet 4, valeur de 0 à 31), compteur_répétitions (int, octet 5, valeur de 0 à 255), position_courante (int, octet 6, valeur de 0 à 31)
3. IF le périphérique ne répond pas dans le délai de 1000 ms ou retourne une réponse de longueur différente de 8 octets, THEN THE Transport SHALL lever une exception indiquant l'échec de lecture du Play State

### Requirement 11: Server Tickle (Watchdog)

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir activer un mécanisme watchdog qui joue automatiquement un pattern si Home Assistant cesse de communiquer avec le blink(1), afin de signaler visuellement une perte de connexion.

#### Acceptance Criteria

1. WHEN l'activation du Server_Tickle est demandée avec un délai en millisecondes (entre 10 et 655350), une position de début (0–31) et une position de fin (0–31), THE Transport SHALL envoyer un Feature_Report de 9 octets avec le report_id 0x01, la commande 'D' (0x44), le flag on=1, le timeout exprimé en unités de 10ms encodé en big-endian sur 2 octets, le flag stay=0, la position de début et la position de fin
2. WHEN la désactivation du Server_Tickle est demandée, THE Transport SHALL envoyer un Feature_Report de 9 octets avec le report_id 0x01, la commande 'D' (0x44), le flag on=0 et les octets restants à 0x00
3. WHILE le Server_Tickle est actif, THE Service_HA SHALL renvoyer le même Feature_Report d'activation à un intervalle ne dépassant pas 50% du délai configuré afin de prévenir l'expiration du timeout
4. IF le délai demandé est inférieur à 10ms ou supérieur à 655350ms, THEN THE Transport SHALL rejeter la commande avec une erreur indiquant les bornes acceptables (10–655350ms)
5. IF la position de début ou la position de fin est supérieure à 31, ou si la position de début est supérieure à la position de fin, THEN THE Transport SHALL rejeter la commande avec une erreur indiquant les contraintes de position

### Requirement 12: Service HA de gestion des patterns

**User Story:** En tant qu'utilisateur Home Assistant, je veux disposer de services HA pour gérer les patterns du blink(1), afin de les configurer depuis l'interface ou les automatisations.

#### Acceptance Criteria

1. THE Service_HA SHALL exposer un service `blink1_status.set_pattern_line` acceptant les paramètres : position (int 0-31), red (int 0-255), green (int 0-255), blue (int 0-255), fade_ms (int 0-655350), et optionnellement led (int 0-2, défaut 0)
2. THE Service_HA SHALL exposer un service `blink1_status.get_pattern_line` acceptant le paramètre position (int 0-31) et retournant la Pattern_Line lue sous forme de dictionnaire { r, g, b, fade_ms }
3. THE Service_HA SHALL exposer un service `blink1_status.save_pattern` sans paramètre pour sauvegarder les patterns en flash
4. THE Service_HA SHALL exposer un service `blink1_status.clear_pattern` sans paramètre pour effacer toutes les lignes de pattern en RAM
5. THE Service_HA SHALL exposer un service `blink1_status.write_pattern` acceptant une chaîne de pattern au format "R,G,B,fade_ms;R,G,B,fade_ms;..." pour écrire un pattern complet aux positions consécutives à partir de 0
6. THE Service_HA SHALL exposer un service `blink1_status.read_pattern` acceptant les paramètres start (int 0-31) et end (int 0-31, end > start) pour lire un pattern complet et retourner la chaîne formatée
7. IF un paramètre est hors de ses bornes valides, THEN THE Service_HA SHALL rejeter l'appel avec une erreur de validation indiquant le paramètre invalide et les bornes acceptables

### Requirement 13: Service HA de contrôle du Play Loop

**User Story:** En tant qu'utilisateur Home Assistant, je veux disposer de services HA pour démarrer et arrêter la lecture des patterns, afin de contrôler les animations depuis l'interface.

#### Acceptance Criteria

1. THE Service_HA SHALL exposer un service `blink1_status.play_pattern` acceptant les paramètres : start (int 0-31), end (int 0-31, end > start), count (int 0-255, défaut 0 pour infini)
2. THE Service_HA SHALL exposer un service `blink1_status.stop_pattern` sans paramètre pour arrêter la lecture en cours
3. THE Service_HA SHALL exposer un service `blink1_status.play_state` sans paramètre retournant un dictionnaire { playing (bool), play_start (int), play_end (int), play_count (int), play_pos (int) }
4. IF un paramètre est hors de ses bornes valides, THEN THE Service_HA SHALL rejeter l'appel avec une erreur de validation indiquant le paramètre invalide

### Requirement 14: Service HA d'effets visuels (Blink/Flash)

**User Story:** En tant qu'utilisateur Home Assistant, je veux disposer de services HA pour déclencher des effets visuels comme le clignotement, afin de créer des notifications visuelles.

#### Acceptance Criteria

1. THE Service_HA SHALL exposer un service `blink1_status.blink` acceptant les paramètres : red (int 0-255), green (int 0-255), blue (int 0-255), count (int 1-255, défaut 3), fade_ms (int 0-655350, défaut 300), led (int 0-2, défaut 0)
2. WHEN le service blink est appelé, THE Service_HA SHALL écrire un pattern temporaire de 2 lignes (couleur spécifiée à la position 0, noir à la position 1) et démarrer un Play_Loop sur les positions 0–2 avec le nombre de répétitions demandé
3. WHEN le clignotement est terminé, THE Service_HA SHALL restaurer les Pattern_Lines aux positions 0 et 1 à leurs valeurs précédentes
4. IF un service blink est appelé alors qu'un clignotement précédent est en cours, THEN THE Service_HA SHALL annuler le clignotement en cours et démarrer le nouveau
5. IF un paramètre est hors de ses bornes valides, THEN THE Service_HA SHALL rejeter l'appel avec une erreur de validation

### Requirement 15: Service HA du Server Tickle

**User Story:** En tant qu'utilisateur Home Assistant, je veux disposer de services HA pour activer et désactiver le watchdog, afin de surveiller la connectivité de Home Assistant depuis la LED.

#### Acceptance Criteria

1. THE Service_HA SHALL exposer un service `blink1_status.enable_server_tickle` acceptant les paramètres : timeout_ms (int, compris entre 100 et 655350), start (int, position de pattern 0–31), end (int, position de pattern 0–31, end > start)
2. THE Service_HA SHALL exposer un service `blink1_status.disable_server_tickle` sans paramètre
3. WHEN le service `enable_server_tickle` est appelé, THE Service_HA SHALL démarrer une tâche asynchrone qui envoie la commande server tickle enable au device à un intervalle égal à la moitié du timeout_ms configuré
4. WHEN le service `disable_server_tickle` est appelé, THE Service_HA SHALL annuler la tâche asynchrone de keepalive et envoyer la commande server tickle disable au device
5. WHEN l'intégration est déchargée (unload) alors que le Server_Tickle est actif, THE Service_HA SHALL annuler la tâche asynchrone de keepalive et envoyer la commande server tickle disable au device avant la fermeture du transport
6. IF le service `enable_server_tickle` est appelé alors qu'un Server_Tickle est déjà actif, THEN THE Service_HA SHALL annuler la tâche précédente et démarrer une nouvelle tâche avec les nouveaux paramètres

### Requirement 16: Lecture de l'état du dispositif

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir lire l'état complet du blink(1) (couleur courante, version firmware, état de lecture), afin de diagnostiquer et monitorer le périphérique.

#### Acceptance Criteria

1. THE Service_HA SHALL exposer un service `blink1_status.get_device_state` retournant un dictionnaire contenant : firmware_version (str), current_color (dict avec r (int 0-255), g (int 0-255), b (int 0-255)), play_state (dict avec playing (bool), play_start (int), play_end (int), play_count (int), play_pos (int))
2. WHEN le service `get_device_state` est appelé, THE Service_HA SHALL lire séquentiellement la version firmware, la couleur courante et l'état de lecture depuis le Transport, chaque opération de lecture devant se terminer dans un délai maximal de 5 secondes
3. IF une des lectures Transport échoue (erreur HID ou timeout dépassé), THEN THE Service_HA SHALL retourner une erreur de service indiquant quelle opération a échoué

### Requirement 17: Support de lecture HID dans le Transport

**User Story:** En tant que développeur, je veux que le Transport supporte la lecture de réponses HID en plus de l'écriture, afin de permettre les commandes de lecture (couleur, version, play state, pattern line).

#### Acceptance Criteria

1. THE Transport base class SHALL exposer une méthode `read(report_id: int) -> bytes` retournant les octets de la réponse HID du périphérique
2. WHEN la méthode read est appelée sur LinuxHidrawTransport, THE Transport SHALL effectuer un appel ioctl HIDIOCGFEATURE pour lire le feature report du descripteur de fichier ouvert
3. WHEN la méthode read est appelée sur PyHidTransport, THE Transport SHALL appeler la méthode `get_feature_report(report_id, length)` du périphérique HID avec une longueur de 9 octets
4. IF aucune réponse n'est disponible dans un délai de 1 seconde, THEN THE Transport SHALL lever une exception TimeoutError avec un message indiquant le dépassement du délai
5. IF la réponse retournée contient moins de 8 octets, THEN THE Transport SHALL lever une exception OSError indiquant une réponse tronquée

### Requirement 18: Parsing et formatage de chaînes de patterns

**User Story:** En tant qu'utilisateur Home Assistant, je veux pouvoir exprimer des patterns complets sous forme de chaînes lisibles (format "R,G,B,fade_ms;..."), afin de faciliter la configuration et le partage de patterns.

#### Acceptance Criteria

1. WHEN une chaîne de pattern au format "R,G,B,fade_ms;R,G,B,fade_ms;..." est fournie (maximum 32 segments), THE Service_HA SHALL parser chaque segment séparé par des points-virgules, extraire les 4 composantes séparées par des virgules (R 0-255, G 0-255, B 0-255, fade_ms 0-655350 par incréments de 10ms) et écrire les Pattern_Lines aux positions consécutives à partir de la position 0
2. WHEN un pattern est lu depuis le dispositif entre une position de début et une position de fin, THE Service_HA SHALL formater les Pattern_Lines en une chaîne au format "R,G,B,fade_ms;R,G,B,fade_ms;..." sans espace superflu
3. FOR ALL chaînes de pattern valides, parser puis formater SHALL produire une chaîne identique (propriété aller-retour)
4. IF la chaîne de pattern contient plus de 32 segments, THEN THE Service_HA SHALL rejeter la chaîne avec un message d'erreur indiquant la limite maximale de 32 segments
5. IF un segment contient un nombre de composantes différent de 4, ou des valeurs non numériques, ou des valeurs RGB hors de 0-255, ou un fade_ms hors de 0-655350, THEN THE Service_HA SHALL rejeter la chaîne avec un message d'erreur indiquant la position du segment invalide et la nature de l'erreur
6. IF la chaîne est vide ou ne contient que des espaces, THEN THE Service_HA SHALL rejeter la chaîne avec un message d'erreur indiquant qu'au moins un segment est requis
