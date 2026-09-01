# JAYU Equity Long Auditor

Agente auditor para acciones USA, solo en largo, conectado a FARO por webhook.

El agente no ejecuta operaciones reales. Por defecto funciona en modo auditor:

- `AUDIT_ONLY=true`
- `DRY_RUN=true`
- `direction=LONG` obligatorio
- mínimo de confianza configurable, por defecto `80`

## Qué hace

1. Lee una watchlist de acciones.
2. Evalúa el régimen de mercado usando `SPY`, `QQQ` e `IWM`.
3. Obtiene datos diarios con Yahoo Finance.
4. Calcula métricas técnicas simples y auditables.
5. Pide a OpenAI una decisión estructurada.
6. Envía a FARO solo señales `LONG` de alta calidad.

Si no hay ventaja, devuelve `NO_TRADE`.

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Rellena:

```env
OPENAI_API_KEY=
FARO_WEBHOOK_URL=
FARO_API_TOKEN=
FARO_PROCESS_ID=jayu-equity-long-auditor
FARO_STRATEGY_ID=equity-long-swing-d1
```

Para probar sin enviar a FARO:

```bash
DRY_RUN=true python -m src.main
```

Para enviar señales auditadas a FARO:

```bash
DRY_RUN=false AUDIT_ONLY=true python -m src.main
```

## GitHub Actions

El workflow `.github/workflows/scan.yml` puede ejecutar el scanner cada hora o manualmente.

Configura estos secrets en GitHub:

- `OPENAI_API_KEY`
- `FARO_WEBHOOK_URL`
- `FARO_API_TOKEN`

Variables opcionales:

- `FARO_PROCESS_ID`
- `FARO_STRATEGY_ID`
- `MIN_CONFIDENCE`
- `MAX_SIGNALS_PER_RUN`
- `WATCHLIST`

## Regla de oro

Este agente prefiere mandar cero señales antes que mandar basura. FARO audita la estadística; no se toca la cuenta real.
