# Guide for the Raspberry Pi evaluation

This guide describes the evaluation setup for the resilient edge gateway.

The evaluation uses a Raspberry Pi for the local gateway and a Windows PC as the upstream MQTT system.

## 1. Evaluation setup

The important separation is:

The local broker runs on:

```text
localhost:1883
```

The upstream broker runs on the Windows PC:

```text
<WINDOWS_IP>:1883
```

The connection from Raspberry Pi to Windows is the only one that is affected. During the degraded conditions and outages the Local message ingestion stays available.

---

## 2. Raspberry Pi setup

Install the packages required for the evaluation:

```bash
sudo apt update

sudo apt install -y \
  git \
  python3-venv \
  python3-pip \
  mosquitto \
  mosquitto-clients \
  sqlite3 \
  iproute2
```

`iproute2` includes `tc`, which is required by NetEm.

Clone and prepare the application:

```bash
git clone https://github.com/Patoruzuy/resilient-edge-gateway.git
cd resilient-edge-gateway

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Enable the local Mosquitto broker:

```bash
sudo systemctl start mosquitto
sudo systemctl enable --now mosquitto
```

Run the test suite before evaluation:

```bash
python -m pytest -v
```

There is a evaluation commands that can be checked with:

make help

---

## 3. Configure the upstream broker

The gateway configuration should use:

```text
Local broker:
localhost:1883

Upstream broker:
<WINDOWS_IP>:1883
```

Before applying an impairment, confirm that the Windows broker is reached through the target Raspberry Pi interface:

```bash
ip route get <WINDOWS_IP>
```

For the evaluation, the route should use the Raspberry Pi upstream interface, for example:

```text
dev wlan0
```

Check that the Windows broker is reachable:

```bash
nc -vz <WINDOWS_IP> 1883
```

---

## 4. Windows upstream system

The Windows PC runs:

* the upstream Mosquitto broker;
* the evaluation collector.

The collector must use the same run ID as the Raspberry Pi experiment.

Start it directly with Python on PowerShell:

```powershell
python -m tools.run_collector `
  --run-id <RUN_ID> `
  --host localhost `
  --port 1883 `
  --database C:\<DIR-CHOICE>\<RUN_ID>\evaluation.db
```

If the repository is stored in OneDrive or another synchronised folder, keep the active evaluation.db outside that folder. When the run is finished, stop the collector before copying the database into the evidence directory in the repository.

---

## 5. Evaluation scenarios

Three runs are used for each of the condition.

| Scenario           | Messages |    Rate | Network condition         |
| ------------------ | -------: | ------: | ------------------------- |
| `DIRECT-BASE`      |      100 | 5 msg/s | Healthy direct path       |
| `GATEWAY-BASE`     |      100 | 5 msg/s | Healthy gateway path      |
| `DEG-100MS-10LOSS` |      100 | 5 msg/s | 100 ms delay and 10% loss |
| `OUT-15S-2HZ`      |       30 | 2 msg/s | Complete upstream outage  |
| `OUT-30S-5HZ`      |      150 | 5 msg/s | Complete upstream outage  |

The numerical scenario configuration is also stored in:

```text
evaluation/scenarios.json
```

---

## 6. Running a gateway experiment

Start gateway ingestion on the Raspberry Pi:

```bash
python -m src
```

The remaining evaluation steps can be run through the Makefile.

Prepare a clean run using:

```bash
make prepare RUN_ID=<RUN_ID>
```

The run should create its own directory under:

```text
evidence/<RUN_ID>/
```

Start the Windows collector before publishing messages.

Generate the required telemetry using:

```bash
make publish RUN_ID=<RUN_ID>
```

```bash
make degraded RUN_ID=<RUN_ID>
```

For an outage scenario:

```bash
make outage RUN_ID=<RUN_ID>
```

When the outage period has finished, restore the upstream connection:

```bash
make clear-netem RUN_ID=<RUN_ID>
```

Then start controlled recovery:

```bash
make recovery RUN_ID=<RUN_ID>
```

For a degraded condition, apply the configured NetEm impairment before publishing or recovery.

## 7. Evidence and reconciliation

Each run keeps its evidence under:

```text
evidence/<RUN_ID>/
```

Depending on the scenario, the directory may have the following files:

```text
publisher_output.csv
gateway.db
evaluation.db
summary.json
reconciliation.csv
timeline.csv
recovery_metrics.json
storage_samples.csv
```

After the Windows collector has been stopped, copy `evaluation.db` into the matching run directory.

The final reconciliation can then be run through the Makefile with these commands:

```bash
make reconcile RUN_ID=<RUN_ID>
```

Reconciliation compares the publisher output, gateway state and collector observations.

## 8. Final checks

Before accepting a run, confirm that the messages were generated, the gateway backlog returned to zero where it meant to, and the collector received the expected messages. Check the reconciliation for missing, duplicate or conflicting observations and make sure all evidence belongs to the correct run.

Finally, clear any remaining NetEm configuration before starting the next experiment:

```bash
make clear-netem
```
