from flask import Flask, render_template,jsonify
from flask_socketio import SocketIO
import serial 
from datetime import datetime
import csv
import threading
from flask_sqlalchemy import SQLAlchemy

# definovanie portu preseriovu komunikaciu, rychlost komunikacie, meno csv suboru na zapisovanie
SERIAL_PORT = '/dev/cu.usbmodem101'
BAUD_RATE = 9600
CSV_FILE = 'file_log.csv'

# instancia flask aplikacie
app = Flask(__name__)
# inicializacia SocketIO pre komunikaciu
socketio = SocketIO(app)

# konfiguracia hesla, vyuzitie sqlite databazy, /// - lokalny subor, db_log.db - databazovy subor
app.config['SECRET_KEY'] = 'heslo'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db_log.db'

#  inicializacia instancie databazy
db = SQLAlchemy(app)

# bool premenne pre seriove spojenie a zasielanie klientovi
serial_initialized = False
client_enabled = False

# trieda databazy: id cislo, casovy udaj, teplota, vlhkost
class db_data(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp_db = db.Column(db.DateTime)
    temperature_db = db.Column(db.Float)
    humidity_db = db.Column(db.Float)

# funkcia pre citanie serial dat
def read_serial():
    file_exists = False # premenna pre overenie existencie suboru
    global serial_initialized 
    print("Serial initialized")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) # premenna pre otvorenie serioveho spojenia
        serial_initialized = True 
        while serial_initialized:
            line = ser.readline().decode('utf-8').strip() # precita serial riadok, na retazec, odstrani medzery
            if ',' in line:
                try:
                    humidity, temperature = map(float, line.split(',')) # zapisanie vlhkosti a teploty do premmennych typu float
                    if client_enabled:
                        timestamp = datetime.now() # premenna s aktualnym casom
                        socketio.emit("sensor_data", {"humidity": humidity, "temperature": temperature}) # odosiela data v r.c. pripojenym web klientom cez SocketIO
                        # ZAPIS DO DATABAZY
                        # vytvorenie flask kontextu (potrebne pre operacie s db)
                        with app.app_context(): 
                            new_entry = db_data(timestamp_db = timestamp,temperature_db=temperature, humidity_db = humidity) # vytvorenie noveho zapisu
                            db.session.add(new_entry) # prida zaznam do db relacie
                            db.session.commit() # potvrdenie na ulozenie do db
                        # ZAPIS DO SUBORU
                        # otvorenie suboru (append mode) a zapis
                        with open(CSV_FILE, mode='a', newline='') as file:
                            writer = csv.writer(file)
                            if file_exists == False:
                                writer.writerow(['Timestamp', 'Temperature[C]', 'Humidity[%]']) # ked subor vytvori zapise prvy riadok
                                file_exists = True
                            row = [timestamp.strftime("%Y-%d-%m %H:%M:%S")] + line.split(',')
                            writer.writerow(row) # zapise riadok
                            file.flush() # zapis na disk
                        print("sent:", line) # vypisanie odoslanych dat klientovi
                    else:
                        print("not sent:",line) # vypisanie neodoslanych dat klientovi 
                except ValueError:
                    continue # preskocenie nepouzitelnych dat
    except serial.SerialException:
        print("Could not open serial port.")

@app.route('/get_data')
# funkcia pre logiku /get_data adresy
def get_data():
    with app.app_context():
        # query na tab. db_data, ekvivalent ku select * from..., 50 riadkov db, zoradene podla casu
        results = db_data.query.order_by(db_data.timestamp_db.desc()).limit(50).all() 
        # db objekt na dictionary
        data = [{
            'timestamp': row.timestamp_db.strftime("%Y-%d-%m %H:%M:%S"),
            "temperature": row.temperature_db,
            "humidity": row.humidity_db
        } 
        for row in results
    ]
    return jsonify(data=data) # konvertuje struktury pythonu do jsonu

# spracovava prikazy prijate od web klientov cez SocketIO
# tlacidla pre zacatie/zastavenie zasielania, zahajenie/ukoncenie ser komunikacie
@socketio.on("command")
def handle_command(cmd):
    global client_enabled, serial_initialized

    print("Received command:", cmd)

    if cmd == "open":
        if not serial_initialized:
            thread = threading.Thread(target=read_serial, daemon=True)
            thread.start()
            print("Measurement initialized")
        else:
            print("Already initialized")

    elif cmd == "start":
        client_enabled = True
        print("Client view enabled")

    elif cmd == "stop":
        client_enabled = False
        print("Client view disabled")

    elif cmd == "close":
        serial_initialized = False
        print("Measurement stopped")

# definovanie home page
@app.route("/")
def index():
    return render_template("index.html") # vykresli subor html

if __name__ == "__main__":
    with app.app_context():
        db.create_all() # vytvori databazove tabulky, ak neexistuju
    socketio.run(app, host="0.0.0.0", port=5000) # spusti server Flask-SocketIO, port 5000
