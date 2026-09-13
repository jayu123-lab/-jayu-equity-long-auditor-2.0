"""JAYU EQUITY LONG SWING — domain model sobre JAYU_BAYES_ENGINE_V1.

Misma matematica que Jayu-Orion y Jayu MT5 (log-odds + likelihood ratios),
pero dominio propio EQUITY_LONG_SWING_V1 con evidencias, priors y
calibracion especificos de acciones USA LONG a horizonte swing
(1-8 semanas). Nunca SHORT. No es un scalper.
"""

DOMAIN_VERSION = "EQUITY_LONG_SWING_V1"
ENGINE_VERSION = "JAYU_BAYES_ENGINE_V1"