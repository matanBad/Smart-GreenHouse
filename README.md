# 🌿 Smart Greenhouse IoT System
> An academic IoT-based monitoring and automation simulation for virtual greenhouse environments, built with Python, Flask, and JavaScript.

![GitHub Maintained](https://img.shields.io/badge/Maintained-Yes-brightgreen)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Framework](https://img.shields.io/badge/Framework-Flask-lightgrey)
![Environment](https://img.shields.io/badge/Environment-Replit-orange)

---

## 📋 Product Overview
The **Smart Greenhouse IoT System** is a software-based IoT prototype designed to monitor and manage environmental conditions inside a virtual greenhouse. By leveraging **four virtual sensors**, the system simulates real-time data collection, evaluates environmental health via a dynamic Rule Engine, generates multi-level severity alerts, and triggers automated actuator simulation to maintain optimal growing conditions.

---

## ⚙️ Core System Capabilities

### 1. Virtual Sensor Monitoring & Data Collection
The system simulates continuous data transmission from four critical agricultural vectors:
* 🌡️ **Temperature Sensor (`Celsius`)**: Tracks heat levels to prevent freezing or overheating.
* 💧 **Air Humidity Sensor (`%`)**: Measures relative atmospheric moisture.
* 🌱 **Soil Moisture Sensor (`%`)**: Monitors root-level hydration to optimize watering cycles.
* ☀️ **Light Intensity Sensor (`Lux`)**: Ensures plants receive adequate exposure for photosynthesis.

### 2. Intelligent Data Validation Layer
To maintain extreme data integrity, every incoming sensor payload is rigorously validated before processing. The system instantly rejects and logs:
* Non-numeric sensor payloads.
* Unconfigured or spoofed Sensor IDs.
* Mismatched units or corrupted timestamps.

### 3. Dynamic Rule Engine & Automated Response
Environmental readings are categorized into **Normal**, **Warning**, or **Critical** states based on administrator-configured threshold objects. When a condition breaches a 'Critical' boundary, the system executes real-world automation logic by triggering simulated actuators:
* **High Temperature** ➡️ Activates **Ventilation / Fans**.
* **Low Soil Moisture** ➡️ Activates **Irrigation Pump**.
* **Low Light Intensity** ➡️ Activates **Artificial Lighting**.
* **High Air Humidity** ➡️ Activates **Air Circulation**.

### 4. Comprehensive Dashboard Experience
* **Greenhouse Health Score**: A high-level algorithmic score summarizing overall greenhouse health for the **Farm Owner**.
* **Active Alerts & Recommended Actions**: Direct behavioral recommendations for the **Greenhouse Manager** upon detecting anomalies.
* **Historical Logs**: Complete auditing tables tracking successful inputs, invalid sensor readings, and administrative threshold alterations.

---

## 🏗️ System Architecture & Workflow
The project implements a strict separation of concerns structured across 7 distinct logical layers:

```text
[Virtual Sensors] ➡️ [REST API Receiver] ➡️ [Validation Module] ➡️ [Rule Engine]
                                                                        ⬇️
[Dashboard UI]   ⬅️   [JSON/SQLite Storage]   ⬅️   [Alerts & Actuator Controllers]


🛠️ Technology StackDevelopment Environment: ReplitBackend: Python 3.x, Flask Web Framework (RESTful API Design)Frontend: Responsive HTML5, Semantic CSS3, Vanilla JavaScript (Fetch API Engine)Storage Layer: Lightweight JSON File Systems / Embedded SQLite DatabaseVersion Control: Git & GitHub🚀 Installation & Local Execution GuideSince this project is fully configured for virtual environments, it can be run directly inside Replit or cloned locally on a host machine.PrerequisitesPython 3.10 or higher installed.Pip (Python Package Installer).Local Setup InstructionsClone the Repository:Bash   git clone [https://github.com/matanBad/Smart-GreenHouse.git](https://github.com/matanBad/Smart-GreenHouse.git)
   cd Smart-GreenHouse
Install Required Framework Dependencies:Bash   pip install flask
Launch the Application Backend:Bash   python main.py
Access the Dashboard:Open your preferred web browser and navigate to: http://127.0.0.1:5000🧪 Predefined Simulation Scenarios (Demo Mode)To easily evaluate system behavior during reviews and grading, the system supports 4 predefined simulation testing scenarios via the dashboard:☀️ Hot Day Scenario: Force-injects high temperature readings to trigger and demonstrate the automatic Ventilation response.🌵 Dry Soil Scenario: Drops soil moisture below the safe threshold to activate simulated Irrigation.☁️ High Humidity Scenario: Spikes relative air humidity to demonstrate Air Circulation behavior.🌙 Low Light Scenario: Minimizes ambient light levels to showcase real-time Artificial Lighting activation.📊 API Reference (Core Endpoints)MethodEndpointDescriptionGET/api/dashboard/statusFetches consolidated greenhouse state, health score, and active sensors.POST/api/sensors/<id>/readingEndpoint for virtual sensors to push structured environmental payloads.GET/api/alerts/activeRetrieves all unresolved warning and critical alerts.PATCH/api/alerts/<id>/resolveMarks an ongoing alert event as manually resolved.PUT/api/thresholds/<sensorType>Allows System Administrators to dynamically update min/max rules.Developed as part of an Academic Project for Smart Agriculture and IoT Simulation Workflows (2026).
