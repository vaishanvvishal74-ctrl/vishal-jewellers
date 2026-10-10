import os
import logging
from datetime import datetime
from functools import wraps

import cloudinary
import cloudinary.uploader

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

logging.basicConfig(level=logging.INFO)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUD_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "").strip()
CLOUD_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

if CLOUD_NAME and CLOUD_API_KEY and CLOUD_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUD_NAME,
        api_key=CLOUD_API_KEY,
        api_secret=CLOUD_API_SECRET,
        secure=True,
    )

database_url = os.environ.get("DATABASE_URL", "sqlite:///jewellers.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
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
    customer_name = db.Column(db.String(150), default="")
    customer_address = db.Column(db.Text, default="")
    payment_method = db.Column(db.String(30), default="COD")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    product_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)


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
    "upi_id": "",
    "upi_qr_url": "",
}


def get_settings():
    result = DEFAULT_SETTINGS.copy()
    for item in Setting.query.all():
        result[item.name] = item.value or ""
    return result


def migrate_database():
    inspector = inspect(db.engine)
    if "order" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("order")}
    additions = {
        "customer_name": "VARCHAR(150) DEFAULT ''",
        "customer_address": "TEXT",
        "payment_method": "VARCHAR(30) DEFAULT 'COD'",
        "created_at": "TIMESTAMP",
    }

    with db.engine.begin() as connection:
        for column, definition in additions.items():
            if column not in existing:
                connection.execute(text(
                    f'ALTER TABLE "order" ADD COLUMN "{column}" {definition}'
                ))


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if ADMIN_PASSWORD and username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        flash("Login galat hai ya Render Environment configure nahi hai.")

    return """
    <!doctype html><html lang="hi"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Vishal Jewellers Admin</title></head>
    <body style="background:#111;color:#e6c875;font-family:Arial;max-width:360px;margin:60px auto;padding:20px">
    <h2>Vishal Jewellers</h2><h3>Admin Login</h3>
    <form method="post">
    <input name="username" placeholder="Username" autocomplete="username" required style="box-sizing:border-box;padding:12px;width:100%;margin:8px 0">
    <input name="password" type="password" placeholder="Password" autocomplete="current-password" required style="box-sizing:border-box;padding:12px;width:100%;margin:8px 0">
    <button type="submit" style="padding:12px;width:100%;background:#e6c875">Login</button>
    </form></body></html>
    """


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/")
def home():
    products = Product.query.order_by(Product.id.desc()).all()
    cart_count = sum(int(q) for q in session.get("cart", {}).values())
    return render_template(
        "index.html", products=products,
        settings=get_settings(), cart_count=cart_count
    )


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/cart")
def cart():
    items = []
    total = 0
    for product_id, quantity in session.get("cart", {}).items():
        product = db.session.get(Product, int(product_id))
        if product:
            quantity = int(quantity)
            subtotal = product.price * quantity
            items.append({"product": product, "quantity": quantity, "subtotal": subtotal})
            total += subtotal
    return render_template("cart.html", items=items, total=total, settings=get_settings())


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash("Product nahi mila.")
        return redirect(url_for("home"))
    if product.stock < 1:
        flash("Yeh product abhi stock mein nahi hai.")
        return redirect(url_for("home"))

    cart_data = session.get("cart", {})
    key = str(product_id)
    quantity = int(cart_data.get(key, 0))
    if quantity >= product.stock:
        flash("Available stock se zyada quantity nahi le sakte.")
    else:
        cart_data[key] = quantity + 1
        session["cart"] = cart_data
        session.modified = True
        flash("Product cart mein add ho gaya.")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart/update", methods=["POST"])
def update_cart():
    cart_data = session.get("cart", {})
    for product_id in list(cart_data.keys()):
        try:
            quantity = int(request.form.get(f"quantity_{product_id}", "1"))
            product = db.session.get(Product, int(product_id))
            if not product or quantity <= 0:
                cart_data.pop(product_id, None)
            else:
                cart_data[product_id] = min(quantity, product.stock)
        except (ValueError, TypeError):
            cart_data.pop(product_id, None)
    session["cart"] = cart_data
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:product_id>", methods=["POST"])
def remove_from_cart(product_id):
    cart_data = session.get("cart", {})
    cart_data.pop(str(product_id), None)
    session["cart"] = cart_data
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart_data = session.get("cart", {})
    if not cart_data:
        flash("Pehle cart mein product add karein.")
        return redirect(url_for("home"))

    items = []
    total = 0
    for product_id, quantity in cart_data.items():
        product = db.session.get(Product, int(product_id))
        if product:
            quantity = int(quantity)
            items.append((product, quantity))
            total += product.price * quantity

    if not items:
        session.pop("cart", None)
        flash("Cart mein koi valid product nahi hai.")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        address = request.form.get("address", "").strip()
        payment_method = request.form.get("payment_method", "COD")

        if not name or len(name) > 150 or not address:
            flash("Naam aur poora delivery address bharna zaroori hai.")
            return redirect(url_for("checkout"))
        if not mobile.isdigit() or len(mobile) != 10:
            flash("Sahi 10 digit mobile number enter karein.")
            return redirect(url_for("checkout"))
        if payment_method not in {"COD", "UPI"}:
            flash("Payment method sahi select karein.")
            return redirect(url_for("checkout"))

        for product, quantity in items:
            db.session.refresh(product)
            if quantity < 1 or quantity > product.stock:
                flash(f"{product.name} ka stock badal gaya hai. Cart check karein.")
                return redirect(url_for("cart"))

        summary = ", ".join(f"{p.name[:35]} x{q}" for p, q in items)[:150]
        order = Order(
            customer_mobile=mobile, customer_name=name,
            customer_address=address, product_name=summary,
            amount=round(total, 2), status="Pending",
            payment_method=payment_method, created_at=datetime.utcnow()
        )

        try:
            db.session.add(order)
            db.session.flush()
            for product, quantity in items:
                db.session.add(OrderItem(
                    order_id=order.id, product_id=product.id,
                    product_name=product.name, quantity=quantity,
                    unit_price=product.price
                ))
                product.stock -= quantity
            db.session.commit()
            order_id = order.id
            session.pop("cart", None)
            return redirect(url_for("order_success", order_id=order_id))
        except Exception:
            db.session.rollback()
            app.logger.exception("Checkout failed")
            flash("Order save nahi hua. Dobara try karein.")
            return redirect(url_for("checkout"))

    return render_template("checkout.html", items=items, total=total, settings=get_settings())


@app.route("/order/success/<int:order_id>")
def order_success(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        flash("Order nahi mila.")
        return redirect(url_for("home"))
    items = OrderItem.query.filter_by(order_id=order.id).all()
    return render_template("order_success.html", order=order, items=items, settings=get_settings())


@app.route("/admin/order/update/<int:order_id>", methods=["POST"])
@admin_required
def update_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        flash("Order nahi mila.")
        return redirect(url_for("admin"))
    allowed = {"Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled"}
    status = request.form.get("status", "")
    if status not in allowed:
        flash("Order status sahi nahi hai.")
        return redirect(url_for("admin"))
    order.status = status
    db.session.commit()
    flash("Order status update ho gaya.")
    return redirect(url_for("admin"))


@app.route("/admin")
@admin_required
def admin():
    return render_template(
        "admin.html", settings=get_settings(),
        products=Product.query.order_by(Product.id.desc()).all(),
        orders=Order.query.order_by(Order.id.desc()).all(),
        order_items=OrderItem.query.order_by(OrderItem.id.asc()).all(),
        customers=Customer.query.count()
    )


@app.route("/admin/settings", methods=["POST"])
@admin_required
def save_settings():
    for name in DEFAULT_SETTINGS:
        if name not in request.form:
            continue
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

    image_url = request.form.get("image_url", "").strip()
    media_file = request.files.get("media")

    if media_file and media_file.filename:
        if not all([CLOUD_NAME, CLOUD_API_KEY, CLOUD_API_SECRET]):
            app.logger.error("Cloudinary environment variables missing.")
            flash("Cloudinary settings configure nahi hain.")
            return redirect(url_for("admin"))

        extension = os.path.splitext(media_file.filename.lower())[1]
        images = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        videos = {".mp4", ".webm", ".mov"}
        if extension not in images | videos:
            flash("Supported files: JPG, PNG, WEBP, GIF, MP4, WEBM, MOV.")
            return redirect(url_for("admin"))

        try:
            media_file.stream.seek(0, 2)
            size = media_file.stream.tell()
            media_file.stream.seek(0)
            if size <= 0 or size > 25 * 1024 * 1024:
                flash("File khaali hai ya 25 MB se badi hai.")
                return redirect(url_for("admin"))

            kind = "video" if extension in videos else "image"
            result = cloudinary.uploader.upload(
                media_file, resource_type=kind,
                folder="vishal-jewellers", timeout=60
            )
            image_url = result.get("secure_url", "")
            if not image_url:
                raise RuntimeError("Cloudinary response did not contain secure_url")
        except Exception as error:
            app.logger.exception("Cloudinary upload failed: %s", type(error).__name__)
            flash("Media upload failed. Render Logs check karein.")
            return redirect(url_for("admin"))

    product = Product(
        name=name,
        category=request.form.get("category", "Gold Jewellery").strip(),
        price=price,
        stock=stock,
        description=request.form.get("description", "").strip(),
        image_url=image_url
    )
    db.session.add(product)
    db.session.commit()
    flash("Product successfully add ho gaya.")
    return redirect(url_for("admin"))


@app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
        flash("Product delete ho gaya.")
    return redirect(url_for("admin"))


@app.route("/register", methods=["GET", "POST"])
def customer_register():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        if not mobile.isdigit() or len(mobile) != 10 or len(password) < 6:
            flash("10 digit mobile aur kam se kam 6 character password dein.")
            return redirect(url_for("customer_register"))
        if Customer.query.filter_by(mobile=mobile).first():
            flash("Is mobile number se account pehle se hai.")
            return redirect(url_for("customer_register"))
        customer = Customer(
            mobile=mobile,
            password_hash=generate_password_hash(password)
        )
        db.session.add(customer)
        db.session.commit()
        session["customer_id"] = customer.id
        return redirect(url_for("customer_account"))
    return render_template("customer_auth.html", mode="register", settings=get_settings())


@app.route("/login", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        customer = Customer.query.filter_by(mobile=mobile).first()
        if customer and check_password_hash(customer.password_hash, password):
            session["customer_id"] = customer.id
            return redirect(url_for("customer_account"))
        flash("Mobile ya password galat hai.")
    return render_template("customer_auth.html", mode="login", settings=get_settings())


@app.route("/account")
def customer_account():
    customer_id = session.get("customer_id")
    if not customer_id:
        return redirect(url_for("customer_login"))
    customer = db.session.get(Customer, customer_id)
    if not customer:
        session.pop("customer_id", None)
        return redirect(url_for("customer_login"))
    orders = Order.query.filter_by(customer_mobile=customer.mobile).order_by(Order.id.desc()).all()
    return render_template("customer_account.html", customer=customer, orders=orders, settings=get_settings())


@app.route("/logout")
def customer_logout():
    session.pop("customer_id", None)
    return redirect(url_for("home"))


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(error):
    flash("Upload file 25 MB se chhoti honi chahiye.")
    return redirect(request.referrer or url_for("admin")), 413


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    app.logger.error("Internal server error: %s", type(error).__name__)
    return "Server error. Render Logs check karein.", 500


with app.app_context():
    db.create_all()
    migrate_database()
    for name, value in DEFAULT_SETTINGS.items():
        if not Setting.query.filter_by(name=name).first():
            db.session.add(Setting(name=name, value=value))
    db.session.commit()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
        
