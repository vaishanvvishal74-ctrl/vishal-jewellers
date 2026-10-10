import os
from functools import wraps

import cloudinary
import cloudinary.uploader

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

# Set these securely in Render Environment Variables.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
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


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if (
            ADMIN_PASSWORD
            and username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))

        flash("Login galat hai ya Render Environment configure nahi hai.")

    messages = "".join(
        f'<p style="color:#ff8080">{message}</p>'
        for category, message in (session.pop("_flashes", []) or [])
    )

    return f"""<!doctype html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vishal Jewellers Admin Login</title>
</head>
<body style="background:#111;color:#e6c875;font-family:Arial;max-width:360px;margin:60px auto;padding:20px">
<h2>Vishal Jewellers</h2>
<h3>Admin Login</h3>
{messages}
<form method="post">
<input name="username" placeholder="Username" autocomplete="username" required style="box-sizing:border-box;padding:12px;width:100%;margin:8px 0">
<input name="password" type="password" placeholder="Password" autocomplete="current-password" required style="box-sizing:border-box;padding:12px;width:100%;margin:8px 0">
<button type="submit" style="padding:12px;width:100%;background:#e6c875">Login</button>
</form>
</body>
</html>"""


@app.route("/admin")
@admin_required
def admin():
    return render_template(
        "admin.html",
        settings=get_settings(),
        products=Product.query.order_by(Product.id.desc()).all(),
        orders=Order.query.order_by(Order.id.desc()).all(),
        customers=Customer.query.count(),
    )


@app.route("/admin/settings", methods=["POST"])
@admin_required
def save_settings():
    for name in DEFAULT_SETTINGS:
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
        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
        api_key = os.environ.get("CLOUDINARY_API_KEY")
        api_secret = os.environ.get("CLOUDINARY_API_SECRET")

        if not all([cloud_name, api_key, api_secret]):
            flash("Cloudinary Environment Variables configure nahi hain.")
            return redirect(url_for("admin"))

        allowed_extensions = {
            ".jpg", ".jpeg", ".png", ".webp", ".gif",
            ".mp4", ".webm", ".mov"
        }
        extension = os.path.splitext(media_file.filename)[1].lower()

        if extension not in allowed_extensions:
            flash("JPG, PNG, WEBP, GIF, MP4, WEBM ya MOV file chunein.")
            return redirect(url_for("admin"))

        try:
            resource_type = (
                "video" if extension in {".mp4", ".webm", ".mov"}
                else "image"
            )
            upload_result = cloudinary.uploader.upload(
                media_file,
                resource_type=resource_type,
                folder="vishal-jewellers",
            )
            image_url = upload_result["secure_url"]
        except Exception:
            app.logger.exception("Cloudinary upload failed")
            flash("Media upload nahi hua. Cloudinary settings check karein.")
            return redirect(url_for("admin"))

    product = Product(
        name=name,
        category=request.form.get("category", "Gold Jewellery").strip(),
        price=price,
        stock=stock,
        description=request.form.get("description", "").strip(),
        image_url=image_url,
    )

    db.session.add(product)
    db.session.commit()
    flash("Product added successfully!")
    return redirect(url_for("admin"))


@app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = db.session.get(Product, product_id)

    if product:
        db.session.delete(product)
        db.session.commit()
        flash("Product deleted.")
    else:
        flash("Product nahi mila.")

    return redirect(url_for("admin"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


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

        if Customer.query.filter_by(mobile=mobile).first():
            flash("Is mobile number se account pehle se hai.")
            return redirect(url_for("register"))

        customer = Customer(
            mobile=mobile,
            password_hash=generate_password_hash(password),
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


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
    
