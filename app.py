import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

from functools import wraps

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-before-deployment"
)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jewellers.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default="")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), default="Gold Jewellery")
    price = db.Column(db.Float, default=0)
    description = db.Column(db.Text, default="")
    image_url = db.Column(db.String(500), default="")
    stock = db.Column(db.Integer, default=0)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_mobile = db.Column(db.String(20), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(40), default="Pending")


class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_percent = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)


DEFAULT_SETTINGS = {
    "shop_name": "Vishal Jewellers",
    "whatsapp": "",
    "instagram": "",
    "email": "",
    "phone": "",
    "address": "",
    "maps_url": "",
    "gold_24k": "",
    "gold_22k": "",
    "gold_18k": "",
    "silver_rate": "",
    "announcement": "Discover Timeless Elegance",
    "theme": "black-gold",
}


def get_settings():
    settings = DEFAULT_SETTINGS.copy()
    for item in Setting.query.all():
        settings[item.name] = item.value or ""
    return settings


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    products = Product.query.order_by(Product.id.desc()).all()
    return render_template(
        "index.html",
        products=products,
        settings=get_settings()
    )


@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    return render_template(
        "admin.html",
        settings=get_settings(),
        products=Product.query.order_by(Product.id.desc()).all(),
        orders=Order.query.order_by(Order.id.desc()).all(),
        customers=Customer.query.count()
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        expected_user = os.environ.get("ADMIN_USERNAME", "admin")
        expected_password = os.environ.get("ADMIN_PASSWORD")

        if not expected_password:
            flash("Admin password server par set nahi hai.")
        elif (
            request.form.get("username") == expected_user
            and request.form.get("password") == expected_password
        ):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            flash("Username ya password galat hai.")

    return """
    <!doctype html>
    <html lang="en">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Vishal Jewellers Admin Login</title>
    <body style="background:#111;color:#e6c875;font-family:Arial;
    max-width:360px;margin:70px auto;padding:20px">
    <h2>Vishal Jewellers</h2>
    <h3>Admin Login</h3>
    <form method="post">
      <input name="username" placeholder="Username"
      required style="padding:12px;width:90%;margin:8px 0">
      <input name="password" type="password" placeholder="Password"
      required style="padding:12px;width:90%;margin:8px 0">
      <button style="padding:12px;width:100%;background:#e6c875">
      Login</button>
    </form>
    </body></html>
    """


@app.route("/admin/settings", methods=["POST"])
@admin_required
def save_settings():
    allowed = set(DEFAULT_SETTINGS)

    for name in allowed:
        value = request.form.get(name, "").strip()
        item = Setting.query.filter_by(name=name).first()

        if item:
            item.value = value
        else:
            db.session.add(Setting(name=name, value=value))

    db.session.commit()
    flash("Website settings saved successfully!")
    return redirect(url_for("admin"))


@app.route("/admin/product/add", methods=["POST"])
@admin_required
def add_product():
    name = request.form.get("name", "").strip()

    if not name:
        flash("Product name zaroori hai.")
        return redirect(url_for("admin"))

    try:
        price = float(request.form.get("price", "0"))
        stock = int(request.form.get("stock", "0"))

        if price < 0 or stock < 0:
            raise ValueError
    except ValueError:
        flash("Price aur stock sahi enter karo.")
        return redirect(url_for("admin"))

    product = Product(
        name=name,
        category=request.form.get("category", "Gold Jewellery"),
        price=price,
        stock=stock,
        description=request.form.get("description", ""),
        image_url=request.form.get("image_url", "")
    )

    db.session.add(product)
    db.session.commit()
    flash("Product added!")
    return redirect(url_for("admin"))


@app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = db.session.get(Product, product_id)

    if product:
        db.session.delete(product)
        db.session.commit()

    flash("Product deleted.")
    return redirect(url_for("admin"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


with app.app_context():
    db.create_all()

from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")

        if not mobile.isdigit() or len(mobile) != 10:
            flash("10 digit ka sahi mobile number enter karo.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password kam se kam 8 characters ka hona chahiye.")
            return redirect(url_for("register"))

        existing = Customer.query.filter_by(mobile=mobile).first()
        if existing:
            flash("Is mobile number se account pehle se hai.")
            return redirect(url_for("register"))

        customer = Customer(
            mobile=mobile,
            password_hash=generate_password_hash(password)
        )
        db.session.add(customer)
        db.session.commit()

        session["customer_mobile"] = mobile
        return redirect(url_for("account"))

    return render_template("customer_auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")

        customer = Customer.query.filter_by(mobile=mobile).first()

        if customer and check_password_hash(customer.password_hash, password):
            session["customer_mobile"] = customer.mobile
            return redirect(url_for("account"))

        flash("Mobile number ya password galat hai.")

    return render_template("customer_auth.html", mode="login")


@app.route("/account")
def account():
    mobile = session.get("customer_mobile")
    if not mobile:
        return redirect(url_for("customer_login"))

    return render_template("customer_account.html", mobile=mobile)


@app.route("/customer/logout")
def customer_logout():
    session.pop("customer_mobile", None)
    return redirect(url_for("home"))
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
