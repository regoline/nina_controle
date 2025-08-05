from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import os
import secrets
import ast

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['SESSION_COOKIE_DOMAIN'] = '.ninacaseira.com'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True  # if using HTTPS

# Database setup
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  is_admin BOOLEAN DEFAULT FALSE)''')
    
    # Recipes table (added yield column)
    c.execute('''CREATE TABLE IF NOT EXISTS recipes
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              unit_price REAL NOT NULL,
              box_price REAL NOT NULL,
              description TEXT,
              created_by INTEGER,
              FOREIGN KEY(created_by) REFERENCES users(id))''')
    
    # Expenses table
    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  amount REAL NOT NULL,
                  description TEXT NOT NULL,
                  date TEXT DEFAULT CURRENT_TIMESTAMP,
                  created_by INTEGER,
                  FOREIGN KEY(created_by) REFERENCES users(id))''')
    
    # Sales table (removed comment from SQL)
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  customer_name TEXT,
                  total_amount REAL NOT NULL,
                  delivery_cost REAL DEFAULT 0,
                  is_delivered BOOLEAN DEFAULT FALSE,
                  is_paid BOOLEAN DEFAULT FALSE,
                  date TEXT DEFAULT CURRENT_TIMESTAMP,
                  created_by INTEGER,
                  FOREIGN KEY(created_by) REFERENCES users(id))''')
    
    # New sales_items table
    c.execute('''CREATE TABLE IF NOT EXISTS sales_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sale_id INTEGER NOT NULL,
                  recipe_id INTEGER NOT NULL,
                  quantity INTEGER NOT NULL,
                  unit_price REAL NOT NULL,
                  box_price REAL NOT NULL,
                  FOREIGN KEY(sale_id) REFERENCES sales(id),
                  FOREIGN KEY(recipe_id) REFERENCES recipes(id))''')             
    
    
    # Check if admin exists
    c.execute("SELECT * FROM users WHERE is_admin = 1")
    if not c.fetchone():
        # Create initial admin with random password
        admin_password = secrets.token_urlsafe(8)
        print(f"\nInitial admin password: {admin_password}\n")
        hashed_pw = generate_password_hash(admin_password)
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                 ('admin', hashed_pw, True))
    
    conn.commit()
    conn.close()

init_db()

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class User(UserMixin):
    pass

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = c.fetchone()
    conn.close()
    
    if user_data:
        user = User()
        user.id = user_data[0]
        user.username = user_data[1]
        user.is_admin = user_data[3]
        return user
    return None

# Auth routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user_data = c.fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data[2], password):
            user = User()
            user.id = user_data[0]
            user.username = user_data[1]
            user.is_admin = user_data[3]
            login_user(user)
            return redirect(url_for('sales'))
        else:
            flash('Usuário ou senha incorretos', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Você não tem permissão para acessar essa página', 'danger')
        return redirect(url_for('recipes'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, username, is_admin FROM users")
    users = c.fetchall()
    conn.close()
    
    return render_template('admin.html', users=users)

@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('Permission denied', 'danger')
        return redirect(url_for('admin'))
    
    username = request.form['username']
    password = request.form['password']
    is_admin = 'is_admin' in request.form
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        hashed_pw = generate_password_hash(password)
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                 (username, hashed_pw, is_admin))
        conn.commit()
        flash('Usuário adicionado com sucesso', 'success')
    except sqlite3.IntegrityError:
        flash('Usuário já existe', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('admin'))

@app.route('/toggle_admin/<int:user_id>')
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash('Permissão negada', 'danger')
        return redirect(url_for('admin'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_admin = NOT is_admin WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    flash('Status de admin atualizado', 'success')
    return redirect(url_for('admin'))
    
@app.route('/recipes')
@login_required
def recipes():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM recipes")
    recipes = c.fetchall()
    conn.close()
    
    return render_template('recipes.html', recipes=recipes)

@app.route('/recipe_cost/<int:recipe_id>')
@login_required
def recipe_cost(recipe_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Get recipe yield
    c.execute("SELECT yield FROM recipes WHERE id = ?", (recipe_id,))
    recipe_yield = c.fetchone()[0]
    
    # Calculate total cost
    c.execute('''SELECT i.name, ri.quantity, i.unit, 
                (i.cost / i.quantity * ri.quantity) AS cost
                FROM recipe_ingredients ri
                JOIN ingredients i ON ri.ingredient_id = i.id
                WHERE ri.recipe_id = ?''', (recipe_id,))
    ingredients = c.fetchall()
    
    total_cost = sum(row[3] for row in ingredients)
    unit_cost = total_cost / recipe_yield if recipe_yield > 0 else 0
    
    conn.close()
    
    return render_template('recipe_cost.html',
                         recipe_id=recipe_id,
                         ingredients=ingredients,
                         total_cost=total_cost,
                         unit_cost=unit_cost,
                         recipe_yield=recipe_yield)

@app.route('/edit_recipe/<int:recipe_id>', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['name']
        unit_price = float(request.form['unit_price'].replace(',', '.'))  # Fix here
        box_price = float(request.form['box_price'].replace(',', '.'))    # And here
        description = request.form.get('description', '')
        
        c.execute("UPDATE recipes SET name = ?, unit_price = ?, box_price = ?, description = ? WHERE id = ?",
                 (name, unit_price, box_price, description, recipe_id))
        
        conn.commit()
        conn.close()
        flash('Receita atualizada com sucesso', 'success')
        return redirect(url_for('recipes'))
    
    c.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,))
    recipe = c.fetchone()
    conn.close()
    
    if not recipe:
        flash('Receita não encontrada', 'danger')
        return redirect(url_for('recipes'))
    
    return render_template('edit_recipe.html', recipe=recipe)

@app.route('/delete_recipe/<int:recipe_id>')
@login_required
def delete_recipe(recipe_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    conn.close()
    
    flash('Receita removida', 'success')
    return redirect(url_for('recipes'))
    
@app.route('/expenses')
@login_required
def expenses():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM expenses ORDER BY date DESC")
    expenses = c.fetchall()
    conn.close()
    
    return render_template('expenses.html', expenses=expenses, datetime=datetime)

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    amount = float(request.form['amount'].replace(',', '.'))
    description = request.form['description']
    date = datetime.strptime(request.form.get('date', datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').strftime('%Y-%m-%d')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO expenses (amount, description, date, created_by) VALUES (?, ?, ?, ?)",
             (amount, description, date, current_user.id))
    conn.commit()
    conn.close()
    
    flash('Gasto incluido com sucesso', 'success')
    return redirect(url_for('expenses'))

# In app.py - edit_expense route
@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        amount = float(request.form['amount'])
        description = request.form['description']
        date = datetime.strptime(request.form['date'], '%d/%m/%Y').strftime('%Y-%m-%d')
        
        c.execute("UPDATE expenses SET amount = ?, description = ?, date = ? WHERE id = ?",
                 (amount, description, date, expense_id))
        conn.commit()
        conn.close()
        flash('Gasto atualizado com sucesso', 'success')
        return redirect(url_for('expenses'))
    
    c.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    expense = c.fetchone()
    conn.close()
    
    if not expense:
        flash('Gasto não localizado', 'danger')
        return redirect(url_for('expenses'))
    
    # Convert date to DD/MM/YYYY format
    expense_date = datetime.strptime(expense[3], '%Y-%m-%d').strftime('%d/%m/%Y') if expense[3] else ''
    expense = list(expense)
    expense[3] = expense_date
    
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete_expense/<int:expense_id>')
@login_required
def delete_expense(expense_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    
    flash('Gasto apagado', 'success')
    return redirect(url_for('expenses'))    

@app.route('/sales')
@login_required
def sales():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Get sales with item counts
    c.execute('''SELECT s.id, s.customer_name, s.total_amount, 
                s.is_delivered, s.is_paid, s.date, s.delivery_cost
                FROM sales s
                ORDER BY s.date DESC''')
    sales_data = c.fetchall()
    
    # Get all sale items
    c.execute('''SELECT si.sale_id, si.quantity, r.name 
                FROM sales_items si
                JOIN recipes r ON si.recipe_id = r.id''')
    sale_items = c.fetchall()
    
    # Get recipes for the form
    c.execute("SELECT id, name, unit_price, box_price FROM recipes")
    recipes = c.fetchall()
    
    conn.close()
    
    return render_template('sales.html', 
                     sales=sales_data, 
                     sale_items=sale_items,
                     recipes=recipes,
                     datetime=datetime)

@app.route('/add_sale', methods=['POST'])
@login_required
def add_sale():
    try:
        customer_name = request.form.get('customer_name', '')
        recipe_ids = request.form.getlist('recipe_id[]')
        quantities = request.form.getlist('quantity[]')
        delivery_cost = float(request.form.get('delivery_cost', '0').replace(',', '.'))
        date_str = request.form.get('date', datetime.now().strftime('%d/%m/%Y'))
        date = datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')

        
        if not recipe_ids or not all(recipe_ids):
            flash('Por favor selecione ao menos 1 receita', 'danger')
            return redirect(url_for('sales'))
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        
        # Insert the sale
        c.execute("""INSERT INTO sales 
                    (customer_name, total_amount, delivery_cost,
                     is_delivered, is_paid, date, created_by)
                    VALUES (?, 0, ?, ?, ?, ?, ?)""",
                 (customer_name, delivery_cost,
                  'is_delivered' in request.form, 'is_paid' in request.form,
                  date, current_user.id))
        
        sale_id = c.lastrowid
        total_amount = 0
        
        # Insert each recipe item
        for recipe_id, quantity in zip(recipe_ids, quantities):
            recipe_id = int(recipe_id)
            quantity = int(quantity)
            
            # Get prices
            c.execute("SELECT unit_price, box_price FROM recipes WHERE id = ?", (recipe_id,))
            unit_price, box_price = c.fetchone()
            
            # Calculate subtotal for this item
            boxes = quantity // 6
            units = quantity % 6
            item_subtotal = (boxes * box_price) + (units * unit_price)
            total_amount += item_subtotal
            
            c.execute("""INSERT INTO sales_items
                        (sale_id, recipe_id, quantity, unit_price, box_price)
                        VALUES (?, ?, ?, ?, ?)""",
                     (sale_id, recipe_id, quantity, unit_price, box_price))
        
        # Update total amount with delivery
        total_amount += delivery_cost
        c.execute("UPDATE sales SET total_amount = ? WHERE id = ?", (total_amount, sale_id))
        
        conn.commit()
        conn.close()
        flash('Venda adicionada com sucesso', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar venda: {str(e)}', 'danger')
    
    return redirect(url_for('sales'))

@app.route('/edit_sale/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def edit_sale(sale_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        customer_name = request.form.get('customer_name', '')
        recipe_ids = request.form.getlist('recipe_id[]')
        quantities = request.form.getlist('quantity[]')
        delivery_cost = float(request.form.get('delivery_cost', '0').replace(',', '.'))
        
        try:
            # Parse date from DD/MM/YYYY to YYYY-MM-DD
            date_str = request.form['date']
            date = datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            flash('Formato inválido de data. Utilize DD/MM/YYYY', 'danger')
            return redirect(url_for('edit_sale', sale_id=sale_id))
        
        # Delete existing items
        c.execute("DELETE FROM sales_items WHERE sale_id = ?", (sale_id,))
        
        total_amount = 0
        
        # Insert new items
        for recipe_id, quantity in zip(recipe_ids, quantities):
            if not recipe_id or not quantity:
                continue
                
            recipe_id = int(recipe_id)
            quantity = int(quantity)
            
            # Get prices
            c.execute("SELECT unit_price, box_price FROM recipes WHERE id = ?", (recipe_id,))
            unit_price, box_price = c.fetchone()
            
            # Calculate subtotal
            boxes = quantity // 6
            units = quantity % 6
            item_subtotal = (boxes * box_price) + (units * unit_price)
            total_amount += item_subtotal
            
            c.execute("""INSERT INTO sales_items
                        (sale_id, recipe_id, quantity, unit_price, box_price)
                        VALUES (?, ?, ?, ?, ?)""",
                     (sale_id, recipe_id, quantity, unit_price, box_price))
        
        # Update sale with delivery cost - FIXED: Correct parameter order including date
        c.execute("""UPDATE sales 
                    SET customer_name = ?, 
                        total_amount = ?,
                        delivery_cost = ?,
                        is_delivered = ?, 
                        is_paid = ?,
                        date = ?
                    WHERE id = ?""",
                 (customer_name, 
                  total_amount + delivery_cost,
                  delivery_cost,
                  'is_delivered' in request.form, 
                  'is_paid' in request.form,
                  date,  # Date parameter added here
                  sale_id))
        
        conn.commit()
        conn.close()
        flash('Venda atualizada com sucesso', 'success')
        return redirect(url_for('sales'))
    
    # GET request handling
    c.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
    sale = list(c.fetchone())  # Convert to list to ensure we can modify it if needed
    
    # Convert date to DD/MM/YYYY format for display
    if sale[6]:  # Assuming date is at index 5
        try:
            sale_date = datetime.strptime(sale[6], '%Y-%m-%d').strftime('%d/%m/%Y')
            sale[6] = sale_date
        except (ValueError, TypeError):
            sale[6] = datetime.now().strftime('%d/%m/%Y')  # Fallback to current date
    
    # Ensure delivery cost is properly formatted (index 3 is delivery_cost)
    if sale and sale[3] is not None:
        sale[3] = float(sale[3])  # Convert to float if it's not already
    
    c.execute("""SELECT si.recipe_id, si.quantity, r.name 
                FROM sales_items si
                JOIN recipes r ON si.recipe_id = r.id
                WHERE si.sale_id = ?""", (sale_id,))
    sale_items = c.fetchall()
    
    c.execute("SELECT id, name, unit_price, box_price FROM recipes")
    recipes = c.fetchall()
    conn.close()
    
    if not sale:
        flash('Venda não encontrada', 'danger')
        return redirect(url_for('sales'))
    
    return render_template('edit_sale.html', 
                         sale=sale, 
                         recipes=recipes,
                         sale_items=sale_items)

@app.route('/delete_sale/<int:sale_id>')
@login_required
def delete_sale(sale_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
    conn.commit()
    conn.close()
    
    flash('Venda apagada', 'success')
    return redirect(url_for('sales'))

@app.route('/toggle_sale_status/<int:sale_id>/<string:status>')
@login_required
def toggle_sale_status(sale_id, status):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if status == 'delivered':
        c.execute("UPDATE sales SET is_delivered = NOT is_delivered WHERE id = ?", (sale_id,))
    elif status == 'paid':
        c.execute("UPDATE sales SET is_paid = NOT is_paid WHERE id = ?", (sale_id,))
    
    conn.commit()
    conn.close()
    
    flash('Satus atualizado', 'success')
    return redirect(url_for('sales'))
    
@app.route('/results')
@login_required
def results():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Get totals
    c.execute("SELECT SUM(total_amount), SUM(delivery_cost) FROM sales")
    total_sales, total_delivery = c.fetchone() or (0, 0)
    
    c.execute("SELECT SUM(amount) FROM expenses")
    total_expenses = c.fetchone()[0] or 0
    
    # Calculate profit
    profit = (total_sales or 0) - (total_expenses or 0)
    
    # Get chart data (last 30 days)
    c.execute("""SELECT date, SUM(total_amount), SUM(amount) 
                 FROM (
                     SELECT date, total_amount, 0 as amount FROM sales
                     UNION ALL
                     SELECT date, 0 as total_amount, amount FROM expenses
                 )
                 WHERE date >= date('now', '-30 days')
                 GROUP BY date
                 ORDER BY date""")
    chart_data = c.fetchall()
    
    # Get recent sales (last 10)
    c.execute("""SELECT id, customer_name, total_amount, delivery_cost, 
                is_delivered, is_paid, date 
                FROM sales 
                ORDER BY date DESC 
                LIMIT 10""")
    recent_sales = c.fetchall()
    
    # Get recent expenses (last 10)
    c.execute("""SELECT id, amount, description, date 
                FROM expenses 
                ORDER BY date DESC 
                LIMIT 10""")
    recent_expenses = c.fetchall()
    
    conn.close()
    
    # Prepare chart labels and datasets with formatted dates
    dates = []
    sales = []
    expenses = []
    
    for row in chart_data:
        # Format date as DD/MM/YYYY
        try:
            date_obj = datetime.strptime(row[0], '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d/%m/%Y')
        except:
            formatted_date = row[0]  # fallback if parsing fails
            
        dates.append(formatted_date)
        sales.append(float(row[1]))
        expenses.append(float(row[2]))
    
    # Format dates in recent sales
    formatted_recent_sales = []
    for sale in recent_sales:
        sale = list(sale)  # convert to list to modify date
        try:
            date_obj = datetime.strptime(sale[6], '%Y-%m-%d')
            sale[6] = date_obj.strftime('%d/%m/%Y')
        except:
            pass  # keep original format if parsing fails
        formatted_recent_sales.append(sale)
    
    # Format dates in recent expenses
    formatted_recent_expenses = []
    for expense in recent_expenses:
        expense = list(expense)  # convert to list to modify date
        try:
            date_obj = datetime.strptime(expense[3], '%Y-%m-%d')
            expense[3] = date_obj.strftime('%d/%m/%Y')
        except:
            pass  # keep original format if parsing fails
        formatted_recent_expenses.append(expense)
    
    return render_template('results.html',
                         total_sales=total_sales,
                         total_delivery=total_delivery,
                         total_expenses=total_expenses,
                         profit=profit,
                         dates=dates,
                         sales=sales,
                         expenses=expenses,
                         recent_sales=formatted_recent_sales,
                         recent_expenses=formatted_recent_expenses)
    
@app.route('/add_recipe', methods=['POST'])
@login_required
def add_recipe():
    name = request.form['name']
    unit_price = float(request.form['unit_price'].replace(',', '.'))
    box_price = float(request.form['box_price'].replace(',', '.'))
    description = request.form.get('description', '')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO recipes (name, unit_price, box_price, description, created_by) VALUES (?, ?, ?, ?, ?)",
             (name, unit_price, box_price, description, current_user.id))
    conn.commit()
    conn.close()
    
    flash('Receita adicionada com sucesso', 'success')
    return redirect(url_for('recipes'))

if __name__ == '__main__':
    app.run(debug=True)
