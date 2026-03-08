# discord-rpc

Plugin 3DS (`.3gx`) base sur Luma3DS-Plugin-sample pour envoyer des evenements UDP vers un PC.

## Objectif

- Recuperer des infos cote 3DS (point de depart: evenements plugin)
- Envoyer des messages UDP vers un PC
- Servir de base pour un bridge Discord Rich Presence

## Configuration

Le fichier `.env` est lu par le `Makefile` a la compilation:

```dotenv
IP_PC="127.0.0.1"
UDP_PORT=5005
```

Tu peux partir de `.env.example` pour creer ton fichier local:

```zsh
cp .env.example .env
```

Variables injectees dans le code:

- `IP_PC_STR`
- `UDP_PORT_NUM`

Valeurs par defaut (si `.env` absent): `127.0.0.1:5005`.

## Comportement actuel du plugin

Dans `Sources/plugin_main.c` (mode automatique):

- envoie `plugin_start` au chargement
- envoie `heartbeat` toutes les 10 secondes
- chaque payload contient uniquement `event` et `titleId`

Exemple de payload JSON:

```json
{"event":"heartbeat","titleId":"00040000000EC300"}
```

Le nom et l'icone ne sont plus envoyes par la 3DS.
Ils sont resolus cote PC via l'API `https://api.nlib.cc/ctr/:tid`.

## Dockerisation complete

Le projet inclut maintenant une image build dediee dans `docker/Dockerfile`.

### Ce que l'image initialise

- base toolchain: `devkitpro/devkitarm`
- build de `3gxtool` depuis `https://gitlab.com/thepixellizeross/3gxtool`
- installation de `3gxtool` dans `/usr/local/bin/3gxtool`
- variable `THREEGXTOOL` preconfiguree pour le `Makefile`

### Construire l'image

```zsh
docker build -f docker/Dockerfile -t ctrpf-drpc-builder .
```

### Build `.3gx` reproductible

```zsh
docker run --rm \
  --env-file .env \
  -v "$PWD":/work \
  -w /work \
  ctrpf-drpc-builder \
  sh -lc "make clean all THREEGXTOOL=/usr/local/bin/3gxtool"
```

### Build `.elf` (sans packaging)

```zsh
docker run --rm \
  --env-file .env \
  -v "$PWD":/work \
  -w /work \
  ctrpf-drpc-builder \
  sh -lc "make clean elf THREEGXTOOL=/usr/local/bin/3gxtool"
```

## Docker Compose

Le fichier `docker-compose.yml` fournit le meme flux avec une commande unique:

```zsh
docker compose run --rm builder
```

## Script helper

Un script est fourni pour simplifier le flux:

- `scripts/docker-build.sh` (target par defaut: `all`)
- target possible: `elf`

Exemples:

```zsh
./scripts/docker-build.sh
./scripts/docker-build.sh elf
```

Variables utiles:

- `IMAGE_NAME` (defaut: `ctrpf-drpc-builder`)
- `DOCKERFILE_PATH` (defaut: `docker/Dockerfile`)
- `THREEGXTOOL_REPO` (defaut: `https://gitlab.com/thepixellizeross/3gxtool`)
- `THREEGXTOOL_REF` (defaut: `master`)

## GitHub Actions

Le workflow `/.github/workflows/build-3gx.yml`:

- build l'image Docker (avec `3gxtool`)
- compile le plugin (`make clean all`)
- publie les artefacts (`.3gx`, `.elf`, `.map`) dans l'onglet Actions
- publie les memes fichiers en Release Assets sur les tags `v*`
- cree un `.env` en CI depuis les Secrets `IP_PC` et `UDP_PORT` (ou fallback sur `.env.example`)

Configuration conseillee dans GitHub:

- `Settings > Secrets and variables > Actions > New repository secret`
- ajouter `IP_PC`
- ajouter `UDP_PORT`

## Test UDP cote PC

Lancer le listener UDP avec resolution API:

```zsh
python3 udp_logger.py
```

Le logger ecoute sur `0.0.0.0:5005`, affiche les JSON recus puis une ligne enrichie avec:

- `name` (nom du jeu)
- `icon` (URL de `media.icon`)

Puis lancer le plugin sur la 3DS:

- verifier les evenements `plugin_start` puis `heartbeat`
- verifier que `titleId` est resolu en `name` et `icon`
