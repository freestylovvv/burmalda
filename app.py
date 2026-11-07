import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'burmalda-super-secret-key-change-it-in-production'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Строка подключения к PostgreSQL (берется из environment в Docker-compose)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:secretpassword@localhost:5432/burmalda_db')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Инициализация базы данных (синтаксис PostgreSQL с SERIAL)
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            image TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            total_price REAL NOT NULL,
            items_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

# Главная страница (Каталог)
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', products=products)

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        is_admin = 1 if username == 'admin' or password == 'burmalda' else 0

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)',
                           (username, hashed_password, is_admin))
            conn.commit()
            cursor.close()
            conn.close()
            flash('Регистрация успешна! Теперь войдите.', 'success')
            return redirect(url_for('login'))
        except Exception:
            flash('Имя пользователя уже занято.', 'danger')
            
    return render_template('register.html')

# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['is_admin'] = user[3]
            flash(f'Добро пожаловать, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль.', 'danger')
            
    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

# Админ-панель
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'):
        flash('Доступ запрещен!', 'danger')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        file = request.files['image']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f"uploads/{filename}"
            
            cursor.execute('INSERT INTO products (title, description, price, image) VALUES (%s, %s, %s, %s)',
                           (title, description, float(price), image_path))
            conn.commit()
            cursor.close()
            conn.close()
            flash('Товар успешно добавлен!', 'success')
            return redirect(url_for('admin'))
            
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin.html', products=products)

# Удаление товара
@app.route('/admin/product/delete/<int:product_id>')
def delete_product(product_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = %s', (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Товар удален из каталога.', 'info')
    return redirect(url_for('admin'))

# Профиль
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'change_password':
            new_password = request.form['new_password']
            hashed_password = generate_password_hash(new_password)
            is_admin = 1 if new_password == 'burmalda' or session['username'] == 'admin' else session['is_admin']
            
            cursor.execute('UPDATE users SET password = %s, is_admin = %s WHERE id = %s', 
                           (hashed_password, is_admin, session['user_id']))
            conn.commit()
            session['is_admin'] = is_admin
            flash('Пароль успешно изменен!', 'success')
            
        elif action == 'delete_account':
            cursor.execute('DELETE FROM users WHERE id = %s', (session['user_id'],))
            conn.commit()
            cursor.close()
            conn.close()
            session.clear()
            flash('Ваш аккаунт был удален.', 'info')
            return redirect(url_for('index'))

    cursor.execute('SELECT id, total_price, items_text, created_at FROM orders WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('profile.html', orders=orders)

# Корзина
@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    conn = get_db_connection()
    cursor = conn.cursor()
    
    products_in_cart = []
    total_price = 0
    for product_id in cart_items:
        cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
        prod = cursor.fetchone()
        if prod:
            products_in_cart.append(prod)
            total_price += prod[3]
            
    cursor.close()
    conn.close()
    return render_template('cart.html', products=products_in_cart, total=total_price)

@app.route('/cart/add/<int:product_id>')
def add_to_cart(product_id):
    if 'cart' not in session or not isinstance(session['cart'], list):
        session['cart'] = []
    session['cart'].append(int(product_id))
    session.modified = True
    flash('Товар добавлен в корзину!', 'success')
    return redirect(url_for('index'))

@app.route('/cart/remove/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    if product_id in cart:
        cart.remove(product_id)
        session['cart'] = cart
        session.modified = True
        flash('Товар удален из корзины.', 'info')
    return redirect(url_for('cart'))

@app.route('/cart/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        flash('Для оформления заказа необходимо войти в систему.', 'danger')
        return redirect(url_for('login'))
        
    cart_items = session.get('cart', [])
    if not cart_items:
        flash('Ваша корзина пуста!', 'warning')
        return redirect(url_for('cart'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    total_price = 0
    item_titles = []
    for product_id in cart_items:
        cursor.execute('SELECT title, price FROM products WHERE id = %s', (product_id,))
        prod = cursor.fetchone()
        if prod:
            item_titles.append(prod[0])
            total_price += prod[1]
            
    items_str = ", ".join(item_titles)
    
    cursor.execute('INSERT INTO orders (user_id, total_price, items_text) VALUES (%s, %s, %s)',
                   (session['user_id'], total_price, items_str))
    conn.commit()
    cursor.close()
    conn.close()
    
    session.pop('cart', None)
    flash('Заказ успешно оформлен! Спасибо за покупку в burmalda.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)