# ESP32 — Especificação do Protocolo Serial

> Documento para sincronizar o Pi com o firmware ESP32.  
> O Pi envia texto por UART (115200 baud, `\n` como terminador).  
> Formato: 2 letras de comando + espaço + argumentos (se houver) + `\n`.  
> O ESP32 lê 2 bytes (comando) + 1 byte (separador), executa, responde com texto + `\n`.

---

## Comandos

### `PG` — Ping
- Pi envia: `PG\n`
- ESP32 responde: `OK\n`
- Usado no arranque para confirmar comunicação.

---

### `SR` — Sensor Reading (ultrassónicos)
- Pi envia: `SR\n`
- ESP32 responde: `esq,frente,dir\n`
  - Exemplo: `32,8,45\n`
  - Valores em **cm** (inteiros, sem espaços)
  - Ordem: esquerda, frente, direita **relativas ao robot**
  - **3 valores apenas** (sensor traseiro não incluído)

---

### `MZ` — Motor/encoder Zero (reset)
- Pi envia: `MZ\n`
- ESP32 responde: `OK\n`
- Reseta os contadores de encoder de **todos os 4 motores para 0**.
- Chamado pelo Pi antes de iniciar cada movimento.

---

### `MR` — Motor Read (encoders)
- Pi envia: `MR\n`
- ESP32 responde: `e1,e2,e3,e4\n`
  - Exemplo: `10.5,10.2,10.8,10.3\n`
  - Valores em **cm acumulados desde o último `MZ`**
  - **4 valores apenas** — sem ângulo (o Pi calcula heading pela IMU)

> Nota: Os encoders são unsigned — valores são sempre positivos.
> O Pi usa `abs()` internamente para robustez.

---

### `MC v1 v2 v3 v4` — Motor Control
- Pi envia: `MC 40 40 40 40\n` (avançar)
- ESP32 responde: `OK\n`
- Valores: -100 a 100 (inteiros)
- Mapeamento de motores (consistente com o wiring):
  - `v1` = motor frente-esquerda (índice 0)
  - `v2` = motor frente-direita  (índice 1)
  - `v3` = motor trás-esquerda   (índice 2)
  - `v4` = motor trás-direita    (índice 3)
- Exemplo de comandos:
  - Avançar:  `MC 40 40 40 40`
  - Recuar:   `MC -40 -40 -40 -40`
  - Virar direita (in-place): `MC -35 35 -35 35`
  - Virar esquerda (in-place): `MC 35 -35 35 -35`
  - Parar:    `MC 0 0 0 0`

---

### `VC` — Victim Confirmed (kit de resgate)
- Pi envia: `VC\n`
- ESP32 responde: `OK\n`
- Ativa o servomotor de deposição (90° → 1s → 0°).

---

## Compensação lateral (ESP32-side)

O ESP32 aplica automaticamente compensação lateral baseada nos ultrassónicos:

- **Frequência:** a cada 200ms
- **Ativação:** apenas durante translação (todos os motores no mesmo sentido)
- **Desativação:** durante rotação (motores em sentidos opostos) ou parado
- **Lógica:** quanto mais perto da parede lateral, maior a correção de velocidade
  para afastar o robot
- **Fórmula:** `compensação = (threshold - distância) × ganho`
  - `threshold = 10cm`, `ganho = 1.5` (ajustáveis no firmware)
- Os valores comandados pelo Pi (`speeds[]`) **não são alterados** — a compensação
  modifica apenas os valores aplicados aos motores temporariamente
- Os valores de compensação são **cached** entre leituras para serem reaplicados
  imediatamente quando um novo `MC` é recebido

> **Importante:** O Pi pode aplicar correção de heading (via IMU) por cima.
> As duas correções são complementares: Pi corrige desvio angular (longo prazo),
> ESP32 evita colisão lateral (reativo, curto prazo).

---

## Considerações de timing

- Timeout do Pi por comando: **2s** (com retry até 3×)
- O Pi chama `MR` a cada **~10ms** durante movimento — o ESP32 deve responder
  em menos de **50ms** para não causar timeouts.
- `SR` (ultrassónico HC-SR04) demora ~30-60ms — é normal e o Pi aguarda.
- A leitura de ultrassónicos para compensação lateral (2 sensores, ~60ms)
  bloqueia o processamento de comandos temporariamente. Os bytes acumulam
  no buffer UART e são processados imediatamente após.
- O Pi envia `MC 0 0 0 0` para parar. O ESP32 deve parar **imediatamente**
  ao receber este comando, mesmo se estiver no meio de outra operação.

---

## Notas adicionais

- Se o ESP32 receber um comando desconhecido, responde `OK\n` (não falha silenciosamente).
- O Pi faz `reset_input_buffer()` antes de cada envio para limpar lixo do buffer.
- **Não enviar dados não solicitados** — o Pi só lê após enviar; dados espontâneos
  do ESP32 irão corromper a leitura seguinte.
- O ESP32 faz flush de bytes residuais (ex: `\r`) após cada comando.
- `Serial.setTimeout(200)` está configurado para evitar bloqueios longos em `parseInt()`.
