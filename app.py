from flask import Flask, flash, jsonify, render_template, request, redirect, url_for, session
import json
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, db, storage
import os
import uuid
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_key_123"
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
STATUS_TRANSLATE = {
    'available': 'Свободно',
    'booked': 'Занято',
    'closed': 'Закрыто',
    'completed': 'Завершено',
    'pending': 'Ожидание',
    'canceled': 'Отменено'
}

STATUS_COLORS = {
    'available': 'success',
    'booked': 'danger',
    'closed': 'secondary',
    'completed': 'info',
    'pending': 'primary',
    'canceled': 'dark'
}

# Initialize Firebase with environment variables
cred = credentials.Certificate({
    'type': os.getenv('FIREBASE_TYPE'),
    'project_id': os.getenv('FIREBASE_PROJECT_ID'),
    'private_key_id': os.getenv('FIREBASE_PRIVATE_KEY_ID'),
    'private_key': os.getenv('FIREBASE_PRIVATE_KEY'),
    'client_email': os.getenv('FIREBASE_CLIENT_EMAIL'),
    'client_id': os.getenv('FIREBASE_CLIENT_ID'),
    'auth_uri': os.getenv('FIREBASE_AUTH_URI'),
    'token_uri': os.getenv('FIREBASE_TOKEN_URI'),
    'auth_provider_x509_cert_url': os.getenv('FIREBASE_AUTH_PROVIDER_X509_CERT_URL'),
    'client_x509_cert_url': os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
})

firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv('FIREBASE_DATABASE_URL'),
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET')
})

# Get a reference to the database service
firebase_db = db.reference()
# Get a reference to the storage service
bucket = storage.bucket()

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    try:
        if not value:
            return "Дата не указана"
            
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000)
        elif isinstance(value, str):
            # Try different date formats that might come from Firebase
            try:
                # First try ISO format
                dt = datetime.fromisoformat(value)
            except ValueError:
                try:
                    # Try with T separator format
                    if 'T' in value:
                        dt = datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
                    else:
                        # Try simple date format
                        dt = datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    try:
                        # Try timestamp in string format
                        dt = datetime.fromtimestamp(float(value) / 1000)
                    except:
                        return "Некорректная дата"
        else:
            return "Некорректная дата"
            
        return dt.strftime(format.replace('HH', '%H').replace('mm', '%M').replace('dd', '%d').replace('MM', '%m'))
    
    except Exception as e:
        print(f"Ошибка форматирования даты: {e}")
        return "Некорректная дата"
    
    
def load_db():
    # Get all data from Firebase Realtime Database
    return firebase_db.get()

def save_db(data):
    # This function is kept for compatibility, but we'll use direct updates instead
    pass

# Function to upload a file to Firebase Storage
def upload_file_to_storage(file, folder='images'):
    if not file:
        return None
    
    # Create a unique filename
    filename = secure_filename(file.filename)
    unique_filename = f"{folder}/{uuid.uuid4().hex}_{filename}"
    
    # Upload file to Firebase Storage
    blob = bucket.blob(unique_filename)
    blob.upload_from_file(file)
    
    # Make the file publicly accessible
    blob.make_public()
    
    # Return the public URL
    return blob.public_url

# Function to delete a file from Firebase Storage
def delete_file_from_storage(file_url):
    if not file_url:
        return
    
    try:
        # Extract the path from the URL
        path = file_url.split('/')[-1]
        blob = bucket.blob(f"images/{path}")
        blob.delete()
    except Exception as e:
        print(f"Error deleting file: {e}")

@app.route('/')
def root():
    if 'vet_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'vet_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        doctor_id = request.form.get('doctor_id')
        db = load_db()
        doctors = db.get('doctors', {}) or {}
        
        if doctor_id in doctors:
            session['vet_id'] = doctor_id
            return redirect(url_for('dashboard'))
        return "Ошибка авторизации!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('vet_id', None)
    return redirect(url_for('login'))

def get_appointment_data(appointment):
    db = load_db()
    users = db.get('users', {}) or {}
    pets = db.get('pets', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    owner = users.get(appointment['ownerId'], {})
    pet = pets.get(appointment['petId'], {})
    doctor = doctors.get(appointment['doctorId'], {})

    return {
        **appointment,
        "ownerName": owner.get('name', 'Неизвестно'),
        "petName": pet.get('name', 'Безымянный'),
        "petType": pet.get('type', 'Неизвестный тип'),
        "petAge": pet.get('age', '—'),
        "petPhoto": pet.get('photoUrl', ''),
        "doctorName": doctor.get('name', 'Врач не указан')
    }

def get_stats(db, vet_id):
    today = datetime.today().date()
    
    # Статистика
    appointments = db.get('appointments', {}) or {}
    chats = db.get('chats', {}) or {}
    
    stats = {
        'total_appointments': len([a for a in appointments.values() if a['doctorId'] == vet_id]),
        'active_patients': len(set(a['petId'] for a in appointments.values() if a['doctorId'] == vet_id)),
        'unread_messages': sum(
            1 for chat in chats.values()
            if chat['participants']['doctor'] == vet_id
            for msg in chat.get('messages', {}).values()
            if msg['senderId'] != vet_id  
            and not any(
                reply['senderId'] == vet_id 
                and reply['timestamp'] > msg['timestamp']
                for reply in chat.get('messages', {}).values()
            )),
        'chart_labels': [(today - timedelta(days=i)).strftime("%d.%m") for i in range(6, -1, -1)],
        'chart_data': [
            len([a for a in appointments.values() 
                if a['doctorId'] == vet_id 
                and datetime.fromisoformat(a['date']).date() == (today - timedelta(days=i))
            ]) 
            for i in range(6, -1, -1)
        ]
    }
    
    return stats

def get_recent_events(db, vet_id):
    events = []
    appointments = db.get('appointments', {}) or {}
    
    for appt in appointments.values():
        if appt['doctorId'] == vet_id:
            events.append({
                'title': f"Новый прием: {appt['reason']}",
                'time': datetime.fromisoformat(appt['createdAt']).strftime("%H:%M"),
                'icon': 'calendar-plus',
                'color': 'primary'
            })
    
    return sorted(events, key=lambda x: x['time'], reverse=True)[:5]

@app.route('/dashboard')
def dashboard():
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    vet_id = session['vet_id']
    today = datetime.today().date().isoformat()
    
    appointments = db.get('appointments', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    today_appointments = [
        get_appointment_data(appt) 
        for appt in appointments.values() 
        if appt['doctorId'] == vet_id 
        and appt['date'] == today
    ]
    
    # Фильтрация
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    pet_type_filter = request.args.get('petType')
    
    filtered = [
        get_appointment_data(appt) 
        for appt in appointments.values() 
        if appt['doctorId'] == vet_id
        and (not status_filter or appt['status'] == status_filter)
        and (not date_filter or appt['date'] == date_filter)
        and (not pet_type_filter or appt.get('petType') == pet_type_filter)
    ]
    
    return render_template(
        'dashboard.html',
        status_translate=STATUS_TRANSLATE,
        status_colors=STATUS_COLORS,
        doctor=doctors.get(session['vet_id'], {}),
        today_appointments=today_appointments,
        stats=get_stats(db, vet_id),
        recent_events=get_recent_events(db, vet_id),
        appointments=filtered
    )

@app.route('/patients')
def patients():
    db = load_db()
    search_query = request.args.get('search', '')
    pet_type = request.args.get('type', '')
    
    pets = db.get('pets', {}) or {}
    users = db.get('users', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    # Фильтрация питомцев
    filtered_pets = []
    for pet_id, pet in pets.items():
        if (not search_query or search_query.lower() in pet['name'].lower()) \
           and (not pet_type or pet['type'] == pet_type):
            filtered_pets.append({
                **pet,
                'id': pet_id,
                'owner': users.get(pet['ownerId'], {'name': 'Неизвестно'})['name']
            })
    
    return render_template(
        'patients.html',
        doctor=doctors.get(session['vet_id'], {}),
        pets=filtered_pets,
        search_query=search_query,
        selected_type=pet_type,
        pet_types={'Грызун', 'Кот'} 
    )

@app.route('/patient/<pet_id>')
def patient_details(pet_id):
    db = load_db()
    pets = db.get('pets', {}) or {}
    users = db.get('users', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    pet = pets.get(pet_id)
    
    if not pet:
        return render_template('404.html'), 404
    
    owner = users.get(pet['ownerId'], {})
    return render_template(
        'patient_details.html',
        doctor=doctors.get(session['vet_id'], {}),
        pet=pet,
        owner=owner
    )

@app.route('/appointment/<appointment_id>', methods=['GET', 'POST'])
def appointment_details(appointment_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    appointments = db.get('appointments', {}) or {}
    pets = db.get('pets', {}) or {}
    users = db.get('users', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    appointment = appointments.get(appointment_id)
    if not appointment:
        return "Приём не найден", 404
    
    pet = pets.get(appointment['petId'])
    owner = users.get(appointment['ownerId'])
    health_records = pet.get('HealthRecord', {}) if pet else {}

    if request.method == 'POST':
        appointment['status'] = request.form.get('status')
        appointment['notes'] = request.form.get('notes', '')
        firebase_db.child('appointments').child(appointment_id).set(appointment)
        return redirect(url_for('appointment_details', appointment_id=appointment_id))

    return render_template(
        'appointment_details.html',
        appointment=appointment,
        pet=pet,
        owner=owner,
        health_records=health_records.values(),
        doctor=doctors.get(session['vet_id'], {})
    )

@app.route('/chat')
def chat_list():
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    vet_id = session['vet_id']
    chats = db.get('chats', {}) or {}
    users = db.get('users', {}) or {}
    pets = db.get('pets', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    # Только чаты текущего врача
    vet_chats = {
        k: v for k, v in chats.items() 
        if v['participants']['doctor'] == vet_id
    }
    
    # Клиенты с существующими чатами
    existing_clients = {
        chat['participants']['client'] 
        for chat in vet_chats.values()
    }
    
    return render_template('chat_list.html', 
                         chats=vet_chats,
                         pets=pets,
                         users=users,
                         doctor=doctors.get(vet_id, {}),
                         vet=doctors.get(vet_id, {}),
                         existing_chats=existing_clients)

@app.route('/chat/<chat_id>', methods=['GET', 'POST'])
def chat_detail(chat_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    chats = db.get('chats', {}) or {}
    users = db.get('users', {}) or {}
    pets = db.get('pets', {}) or {}
    doctors = db.get('doctors', {}) or {}
    
    chat = chats.get(chat_id)
    vet_id = session['vet_id']
    
    if not chat or chat['participants']['doctor'] != vet_id:
        return "Чат не найден", 404
    
    client_id = chat['participants']['client']
    owner = users.get(client_id)
    pet = next((p for p in pets.values() if p['ownerId'] == client_id), None)

    if request.method == 'POST':
        message_text = request.form.get('message')
        if message_text:
            new_msg_id = f"msg-{int(datetime.now().timestamp() * 1000)}"
            new_message = {
                "id": new_msg_id,
                "senderId": vet_id,
                "text": message_text,
                "timestamp": int(datetime.now().timestamp() * 1000),
                "user": True
            }
            
            # Update local chat object for template rendering
            if 'messages' not in chat:
                chat['messages'] = {}
            chat['messages'][new_msg_id] = new_message
            
            # Update Firebase
            firebase_db.child('chats').child(chat_id).child('messages').child(new_msg_id).set(new_message)
    
    return render_template(
        'chat_detail.html',
        chat=chat,
        owner=owner,
        doctor=doctors.get(vet_id, {}),
        pet=pet,
        vet=doctors.get(vet_id, {})
    )

@app.route('/start_new_chat/<client_id>')
def start_new_chat(client_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    vet_id = session['vet_id']
    
    # Создаем новый чат
    chat_id = f"{client_id}_{vet_id}"
    new_chat = {
        "participants": {
            "client": client_id,
            "doctor": vet_id
        },
        "messages": {}
    }
    
    firebase_db.child('chats').child(chat_id).set(new_chat)
    
    return redirect(url_for('chat_detail', chat_id=chat_id))

@app.route('/add-weight-record/<pet_id>', methods=['POST'])
def add_weight_record(pet_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    if not pet:
        return "Питомец не найден", 404

    try:
        weight = float(request.form.get('value'))
        date_str = request.form.get('date')
        
        # Ensure consistent date format for Firebase
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
                # Store as ISO format for Firebase
                timestamp = int(date_obj.timestamp() * 1000)  # Конвертируем в миллисекунды
            except ValueError:
                # Try alternative format
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    timestamp = int(date_obj.timestamp() * 1000)
                except ValueError:
                    return "Некорректный формат даты", 400
        else:
            # Use current time if no date provided
            timestamp = int(datetime.now().timestamp() * 1000)
        
        new_record = {
            'id': f"weight-{int(datetime.now().timestamp() * 1000)}",
            'value': weight,
            'date': timestamp,
            'notes': request.form.get('notes', ''),
            'petId': pet_id
        }

        if 'weightHistory' not in pet:
            pet['weightHistory'] = {}
        pet['weightHistory'][new_record['id']] = new_record
        
        # Обновляем статистику
        if 'statistics' not in pet:
            pet['statistics'] = {}
        pet['statistics']['lastWeight'] = weight
        
        firebase_db.child('pets').child(pet_id).set(pet)
    except ValueError as e:
        return f"Ошибка в данных: {str(e)}", 400
    
    return redirect(url_for('patient_details', pet_id=pet_id))

@app.route('/add-health-record/<pet_id>', methods=['POST'])
def add_health_record(pet_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    if not pet:
        return "Питомец не найден", 404

    # Handle photo upload
    photo_urls = []
    if 'photos' in request.files:
        photos = request.files.getlist('photos')
        for photo in photos:
            if photo and photo.filename:
                photo_url = upload_file_to_storage(photo, folder='health_records')
                if photo_url:
                    photo_urls.append(photo_url)

    # Format dates properly for Firebase
    date = request.form.get('date')
    expiration_date = request.form.get('expirationDate')
    
    # Convert dates to ISO format for consistent storage
    if date:
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            date = date_obj.isoformat()
        except ValueError:
            pass  # Keep original format if parsing fails
            
    if expiration_date:
        try:
            exp_date_obj = datetime.strptime(expiration_date, '%Y-%m-%d')
            expiration_date = exp_date_obj.isoformat()
        except ValueError:
            pass  # Keep original format if parsing fails

    new_record = {
        'id': f"rec-{int(datetime.now().timestamp() * 1000)}",
        'title': request.form.get('title'),
        'description': request.form.get('description'),
        'type': request.form.get('type'),
        'date': date,
        'expirationDate': expiration_date,
        'petId': pet_id,
        'photoUrls': photo_urls
    }

    if 'HealthRecord' not in pet:
        pet['HealthRecord'] = {}
    pet['HealthRecord'][new_record['id']] = new_record
    
    firebase_db.child('pets').child(pet_id).set(pet)
    return redirect(url_for('patient_details', pet_id=pet_id))

@app.route('/delete-health-record/<pet_id>/<record_id>')
def delete_health_record(pet_id, record_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    if pet and 'HealthRecord' in pet:
        # Delete photos from Firebase Storage
        health_record = pet['HealthRecord'].get(record_id)
        if health_record and 'photoUrls' in health_record:
            for photo_url in health_record['photoUrls']:
                delete_file_from_storage(photo_url)
                
        # Remove the record from the database
        pet['HealthRecord'].pop(record_id, None)
        firebase_db.child('pets').child(pet_id).set(pet)
    
    return redirect(url_for('patient_details', pet_id=pet_id))

@app.route('/add-recommendation/<pet_id>', methods=['POST'])
def add_recommendation(pet_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    if pet:
        recommendation = request.form.get('text')
        if 'vetRecommendations' not in pet:
            pet['vetRecommendations'] = []
        pet['vetRecommendations'].append(recommendation)
        firebase_db.child('pets').child(pet_id).set(pet)
    
    return redirect(url_for('patient_details', pet_id=pet_id))

@app.route('/delete-recommendation/<pet_id>/<int:index>')
def delete_recommendation(pet_id, index):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    if pet and 'vetRecommendations' in pet and 0 <= index < len(pet['vetRecommendations']):
        pet['vetRecommendations'].pop(index)
        firebase_db.child('pets').child(pet_id).set(pet)
    
    return redirect(url_for('patient_details', pet_id=pet_id))

@app.route('/schedule')
def schedule():
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    vet_id = session['vet_id']
    doctors = db.get('doctors', {}) or {}
    appointments = db.get('appointments', {}) or {}
    pets = db.get('pets', {}) or {}
    
    doctor = doctors.get(vet_id, {})
    selected_date = request.args.get('date', datetime.today().date().isoformat())
    
    # Проверяем рабочий день
    selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
    day_of_week = selected_date_obj.strftime("%A").lower()
    is_working_day = day_of_week in doctor.get('working_days', [])
    
    time_slots = []
    
    if is_working_day:
        base_start = datetime.strptime(doctor.get('base_schedule', {}).get('start', '09:00'), "%H:%M")
        base_end = datetime.strptime(doctor.get('base_schedule', {}).get('end', '18:00'), "%H:%M")
        slot_duration = timedelta(minutes=doctor.get('base_schedule', {}).get('slotDuration', 30))
        
        current_time = base_start
        while current_time <= base_end:
            time_str = current_time.strftime("%H:%M")
            slot_data = {
                'time': time_str,
                'status': 'available',
                'appointment_id': None,
                'pet': None
            }
            
            # Проверка существующих записей
            if doctor.get('schedule', {}).get(selected_date, {}).get(time_str):
                existing = doctor['schedule'][selected_date][time_str]
                slot_data['status'] = existing['status']
                if 'appointmentId' in existing:
                    appointment = appointments.get(existing['appointmentId'])
                    if appointment:
                        slot_data['appointment_id'] = existing['appointmentId']
                        slot_data['pet'] = pets.get(appointment['petId'])
            
            time_slots.append(slot_data)
            current_time += slot_duration
    
    
    # Сбор ближайших приемов
    upcoming = []
    for appt in appointments.values():
        if appt['doctorId'] == vet_id and appt['date'] == selected_date:
            pet = pets.get(appt['petId'], {})
            upcoming.append({
                **appt,
                'petName': pet.get('name', 'Неизвестно'),
                'petPhoto': pet.get('photoUrl', ''),
                'petType': pet.get('type', '')
            })
    
    return render_template(
        'schedule.html',
        status_translate=STATUS_TRANSLATE,
        status_colors=STATUS_COLORS,
        doctor=doctor,
        time_slots=sorted(time_slots, key=lambda x: x['time']),
        selected_date=selected_date,
        booked_slots_count=len([s for s in time_slots if s['status'] == 'booked']),
        total_slots_count=len(time_slots) if is_working_day else 0,
        upcoming_appointments=sorted(upcoming, key=lambda x: (x['date'], x['time']))[:10],
        is_working_day=is_working_day
    )

@app.route('/toggle-slot', methods=['POST'])
def toggle_slot():
    db = load_db()
    vet_id = session['vet_id']
    doctors = db.get('doctors', {}) or {}
    doctor = doctors.get(vet_id, {})
    data = request.json
    
    date = data['date']
    time = data['time']
    
    # Создаем структуру если не существует
    if 'schedule' not in doctor:
        doctor['schedule'] = {}
    
    if date not in doctor['schedule']:
        doctor['schedule'][date] = {}
    
    current = doctor['schedule'].get(date, {}).get(time, {'status': 'available'})
    
    # Переключение статуса
    new_status = 'booked' if current['status'] == 'available' else 'available'
    doctor['schedule'][date][time] = {
        'status': new_status,
        'appointmentId': current.get('appointmentId')
    }
    
    # Update Firebase
    firebase_db.child('doctors').child(vet_id).child('schedule').child(date).child(time).set(doctor['schedule'][date][time])
    
    return jsonify({'success': True, 'new_status': new_status})

@app.route('/update-slot-appointment', methods=['POST'])
def update_slot_appointment():
    db = load_db()
    data = request.json
    vet_id = session['vet_id']
    doctors = db.get('doctors', {}) or {}
    doctor = doctors.get(vet_id, {})
    
    # Создание новой записи
    new_appointment = {
        'id': f"app-{int(datetime.now().timestamp())}",
        'date': data['date'],
        'time': data['time'],
        'doctorId': vet_id,
        'petId': data['petId'],
        'ownerId': data['ownerId'],
        'status': 'booked',
        'reason': data.get('reason', 'Плановый осмотр'),
        'createdAt': datetime.now().isoformat()
    }
    
    # Сохранение в БД
    firebase_db.child('appointments').child(new_appointment['id']).set(new_appointment)
    
    # Обновление расписания врача
    if 'schedule' not in doctor:
        doctor['schedule'] = {}
        
    if data['date'] not in doctor['schedule']:
        doctor['schedule'][data['date']] = {}
    
    doctor['schedule'][data['date']][data['time']] = {
        'status': 'booked',
        'appointmentId': new_appointment['id']
    }
    
    # Update Firebase
    firebase_db.child('doctors').child(vet_id).child('schedule').child(data['date']).child(data['time']).set(doctor['schedule'][data['date']][data['time']])
    
    return jsonify({'success': True})

@app.route('/save-schedule-settings', methods=['POST'])
def save_schedule_settings():
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    data = request.json
    db = load_db()
    vet_id = session['vet_id']
    doctors = db.get('doctors', {}) or {}
    doctor = doctors.get(vet_id, {})
    
    # Сохраняем рабочие дни
    doctor['working_days'] = data.get('working_days', [])
    
    # Сохраняем базовые настройки
    doctor['base_schedule'] = {
        'start': data['base_schedule']['start'],
        'end': data['base_schedule']['end'],
        'slotDuration': int(data['base_schedule']['slotDuration'])
    }
    
    # Сохраняем существующие записи
    if 'schedule' not in doctor:
        doctor['schedule'] = {}
    
    # Обновляем временные слоты
    base_start = datetime.strptime(doctor['base_schedule']['start'], "%H:%M")
    base_end = datetime.strptime(doctor['base_schedule']['end'], "%H:%M")
    slot_duration = doctor['base_schedule']['slotDuration']
    
    current_time = base_start
    while current_time <= base_end:
        current_time += timedelta(minutes=slot_duration)
    
    # Update Firebase with all doctor data
    firebase_db.child('doctors').child(vet_id).set(doctor)
    
    return jsonify({'success': True})

@app.route('/get-slot-details')
def get_slot_details():
    time = request.args.get('time')
    date = request.args.get('date')
    appointment_id = request.args.get('appointmentId')
    
    db = load_db()
    vet_id = session['vet_id']
    doctors = db.get('doctors', {}) or {}
    appointments = db.get('appointments', {}) or {}
    pets = db.get('pets', {}) or {}
    users = db.get('users', {}) or {}
    
    doctor = doctors.get(vet_id, {})
    
    if appointment_id:
        appointment = appointments.get(appointment_id)
        pet = pets.get(appointment['petId']) if appointment else None
        owner = users.get(appointment['ownerId']) if appointment else None
        health_records = pet.get('HealthRecord', {}) if pet else {}
        
        return render_template('partials/slot_details_booked.html', 
                            appointment=appointment,
                            pet=pet,
                            owner=owner,
                            status_translate=STATUS_TRANSLATE,
                            status_colors=STATUS_COLORS,
                            health_records=health_records.values(),
                            time=time,
                            date=date)
    else:
        all_pets = list(pets.values())
        owners = {user_id: user for user_id, user in users.items()}
        
        for pet in all_pets:
            pet['owner'] = owners.get(pet['ownerId'], {'name': 'Неизвестно', 'phone': '—'})
        
        return render_template('partials/slot_details_available.html',
                            time=time,
                            date=date,
                            pets=all_pets,
                            doctor=doctor)

@app.route('/get-appointment-details')
def get_appointment_details():
    appointment_id = request.args.get('id')
    db = load_db()
    appointments = db.get('appointments', {}) or {}
    pets = db.get('pets', {}) or {}
    users = db.get('users', {}) or {}
    
    appointment = appointments.get(appointment_id)
    
    if not appointment:
        return "Приём не найден", 404
    
    pet = pets.get(appointment['petId'])
    owner = users.get(appointment['ownerId'])
    health_records = pet.get('HealthRecord', {}) if pet else {}
    
    return render_template('partials/appointment_details.html',
                         appointment=appointment,
                         pet=pet,
                         owner=owner,
                         health_records=health_records.values())

@app.route('/get-schedule-settings')
def get_schedule_settings():
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    vet_id = session['vet_id']
    doctors = db.get('doctors', {}) or {}
    doctor = doctors.get(vet_id, {})
    
    return jsonify({
        'working_days': doctor.get('working_days', []),
        'base_schedule': doctor.get('base_schedule', {})
    })

@app.route('/complete-appointment/<appointment_id>', methods=['POST'])
def complete_appointment(appointment_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    appointments = db.get('appointments', {}) or {}
    appointment = appointments.get(appointment_id)
    
    if appointment:
        appointment['status'] = 'completed'
        firebase_db.child('appointments').child(appointment_id).set(appointment)
    
    return jsonify({'success': True})

@app.route('/book-slot', methods=['POST'])
def book_slot():
    try:
        if 'vet_id' not in session:
            return redirect(url_for('login'))
        
        date = request.form.get('date')
        time = request.form.get('time')
        pet_id = request.form.get('pet_id')
        reason = request.form.get('reason')
        notes = request.form.get('notes', '')

        # Валидация полей
        if not all([date, time, pet_id, reason]):
            flash('Заполните все обязательные поля')
            return redirect(request.referrer)

        db = load_db()
        vet_id = session['vet_id']
        doctors = db.get('doctors', {}) or {}
        pets = db.get('pets', {}) or {}

        # Проверка существования питомца
        pet = pets.get(pet_id)
        if not pet:
            flash('Питомец не найден')
            return redirect(request.referrer)

        # Проверка занятости слота
        doctor = doctors.get(vet_id, {})
        if doctor.get('schedule', {}).get(date, {}).get(time, {}).get('status') == 'booked':
            flash('Это время уже занято')
            return redirect(request.referrer)

        # Создание записи
        appointment_id = f"app-{int(datetime.now().timestamp() * 1000)}"
        appointment = {
            'id': appointment_id,
            'date': date,
            'time': time,
            'doctorId': vet_id,
            'petId': pet_id,
            'ownerId': pet['ownerId'],
            'reason': reason,
            'status': 'pending',
            'notes': notes,
            'createdAt': datetime.now().isoformat()
        }

        # Сохранение данных в Firebase
        firebase_db.child('appointments').child(appointment_id).set(appointment)

        # Обновление расписания
        if 'schedule' not in doctor:
            doctor['schedule'] = {}
            
        if date not in doctor['schedule']:
            doctor['schedule'][date] = {}
            
        doctor['schedule'][date][time] = {
            'status': 'booked',
            'appointmentId': appointment_id,
            'timestamp': datetime.now().isoformat()
        }

        # Update Firebase
        firebase_db.child('doctors').child(vet_id).child('schedule').child(date).child(time).set(doctor['schedule'][date][time])
        
        return redirect(url_for('schedule'))

    except Exception as e:
        return redirect(request.referrer)

@app.route('/close-slot', methods=['POST'])
def close_slot():
    try:
        if 'vet_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        db = load_db()
        vet_id = session['vet_id']
        doctors = db.get('doctors', {}) or {}
        doctor = doctors.get(vet_id, {})
        
        date = data['date']
        time = data['time']
        
        if 'schedule' not in doctor:
            doctor['schedule'] = {}
            
        if date not in doctor['schedule']:
            doctor['schedule'][date] = {}
            
        if time not in doctor['schedule'][date]:
            doctor['schedule'][date][time] = {}
            
        doctor['schedule'][date][time]['status'] = 'closed'
        doctor['schedule'][date][time]['closed_at'] = datetime.now().isoformat()
        
        # Update Firebase with specific path
        firebase_db.child('doctors').child(vet_id).child('schedule').child(date).child(time).set(doctor['schedule'][date][time])
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/update-daily-calories/<pet_id>', methods=['POST'])
def update_daily_calories(pet_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    
    if not pet:
        return "Питомец не найден", 404
    
    # Получаем данные из формы
    daily_calories = request.form.get('dailyCalories', 0)
    notes = request.form.get('notes', '')
    
    # Инициализируем структуру питания, если она отсутствует
    if 'nutrition' not in pet:
        pet['nutrition'] = {}
    
    # Обновляем данные о калориях
    pet['nutrition']['dailyCalories'] = int(daily_calories)
    pet['nutrition']['lastUpdated'] = datetime.now().isoformat()
    
    # Сохраняем в Firebase
    firebase_db.child('pets').child(pet_id).set(pet)
    
    return redirect(url_for('patient_details', pet_id=pet_id))

@app.route('/add-feeding-record/<pet_id>', methods=['POST'])
def add_feeding_record(pet_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    
    if not pet:
        return "Питомец не найден", 404
    
    try:
        # Получаем данные из формы
        feeding_type = request.form.get('type')
        food_name = request.form.get('foodName')
        quantity = int(request.form.get('quantity'))
        comment = request.form.get('comment', '')
        
        # Обрабатываем дату
        date_str = request.form.get('date')
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                # Создаем структуру для feedingTime как в db.json
                feeding_time = {
                    "chronology": {
                        "calendarType": "iso8601",
                        "id": "ISO"
                    },
                    "dayOfMonth": date_obj.day,
                    "dayOfWeek": date_obj.strftime('%A').upper(),
                    "dayOfYear": date_obj.timetuple().tm_yday,
                    "hour": date_obj.hour,
                    "minute": date_obj.minute,
                    "month": date_obj.strftime('%B').upper(),
                    "monthValue": date_obj.month,
                    "nano": 0,
                    "second": date_obj.second,
                    "year": date_obj.year
                }
            except ValueError:
                return "Некорректный формат даты", 400
        else:
            now = datetime.now()
            feeding_time = {
                "chronology": {
                    "calendarType": "iso8601",
                    "id": "ISO"
                },
                "dayOfMonth": now.day,
                "dayOfWeek": now.strftime('%A').upper(),
                "dayOfYear": now.timetuple().tm_yday,
                "hour": now.hour,
                "minute": now.minute,
                "month": now.strftime('%B').upper(),
                "monthValue": now.month,
                "nano": 0,
                "second": now.second,
                "year": now.year
            }
        
        # Создаем новую запись о кормлении
        record_id = f"-{uuid.uuid4().hex[:16]}"
        new_record = {
            'id': record_id,
            'type': feeding_type,
            'foodName': food_name,
            'quantity': quantity,
            'comment': comment,
            'feedingTime': feeding_time,
            'petId': pet_id
        }
        
        # Инициализируем структуру питания, если она отсутствует
        if 'nutrition' not in pet:
            pet['nutrition'] = {}
        
        # Инициализируем записи о кормлении, если они отсутствуют
        if 'feedingRecords' not in pet['nutrition']:
            pet['nutrition']['feedingRecords'] = {}
        
        # Добавляем новую запись
        pet['nutrition']['feedingRecords'][record_id] = new_record
        pet['nutrition']['lastUpdated'] = datetime.now().isoformat()
        
        # Сохраняем в Firebase
        firebase_db.child('pets').child(pet_id).set(pet)
        
        return redirect(url_for('patient_details', pet_id=pet_id))
    
    except ValueError as e:
        return f"Ошибка в данных: {str(e)}", 400

@app.route('/delete-feeding-record/<pet_id>/<record_id>')
def delete_feeding_record(pet_id, record_id):
    if 'vet_id' not in session:
        return redirect(url_for('login'))
    
    db = load_db()
    pets = db.get('pets', {}) or {}
    pet = pets.get(pet_id)
    
    if pet and 'nutrition' in pet and 'feedingRecords' in pet['nutrition']:
        # Удаляем запись о кормлении
        pet['nutrition']['feedingRecords'].pop(record_id, None)
        pet['nutrition']['lastUpdated'] = datetime.now().isoformat()
        
        # Сохраняем в Firebase
        firebase_db.child('pets').child(pet_id).set(pet)
    
    return redirect(url_for('patient_details', pet_id=pet_id))

if __name__ == '__main__':
    app.run(debug=True)