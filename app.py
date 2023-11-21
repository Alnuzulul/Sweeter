from pymongo import MongoClient
import jwt
from datetime import datetime, timedelta
import hashlib
from dotenv import load_dotenv
from os.path import join, dirname
import os
from flask import Flask, render_template, jsonify, request, redirect, url_for
from werkzeug.utils import secure_filename


# Environment key
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)


SECRET_KEY = os.environ.get("SECRET_KEY")
MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DB_NAME")
TOKEN_KEY = os.environ.get("TOKEN_KEY")

# * Database
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

app = Flask(__name__)

app.config["TEMPLATE_AUTO_RELOAD"] = True
app.config["UPLOAD_FOLDER"] = "./static/img/profile"

# * Function Routing
@app.route("/", methods=["GET"])
def home():
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        user_info = db.users.find_one({"username": payload.get("username")})
        
        return render_template(
            "index.html", user_info=user_info
        )
    except jwt.ExpiredSignatureError:
        msg = "Your token has expired"
        return redirect(url_for("login", msg=msg))
    except jwt.exceptions.DecodeError:
        msg = "There was a problem logging your in"
        return redirect(url_for("login", msg=msg))


@app.route("/login", methods=["GET"])
def login():
    msg = request.args.get("msg")
    return render_template("login.html", msg=msg)


@app.route("/user/<username>", methods=["GET"])
def user(username):
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        print(payload)
        status = username == payload.get("username")
        user_info = db.users.find_one({"username": username}, {"_id": False})
        return render_template("user.html", user_info=user_info, status=status)
    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("home"))


@app.route("/sign_in", methods=["POST"])
def sign_in():
    username_receive = request.form["username_give"]
    password_receive = request.form["password_give"]
    pw_hash = hashlib.sha256(password_receive.encode("utf-8")).hexdigest()
    result = db.users.find_one(
        {
            "username": username_receive,
            "password": pw_hash,
        }
    )
    if result:
        payload = {
            "username": username_receive,
            # the token will be valid for 24 hours
            "exp": datetime.utcnow() + timedelta(seconds=60 * 60 * 24),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        print(token)
        return jsonify(
            {
                "result": "success",
                "token": token,
            }
        )
    else:
        return jsonify(
            {
                "result": "fail",
                "msg": "We could not find a user with that id/password combination",
            }
        )


@app.route("/sign_up/save", methods=["POST"])
def sign_up():
    username_receive = request.form["username_give"]
    password_receive = request.form["password_give"]
    password_hash = hashlib.sha256(password_receive.encode("utf-8")).hexdigest()
    doc = {
        "username": username_receive,  # id username
        "password": password_hash,  # password
        "profile_name": username_receive,  # user's name is set to their id by default
        "profile_pic": "",  # profile image file name
        "profile_pic_real": "img/profile/example.png",  # a default profile image
        "profile_info": "",  # a profile description
    }
    db.users.insert_one(doc)
    return jsonify({"result": "success"})


@app.route("/sign_up/check_dup", methods=["POST"])
def check_dup():
    username_receive = request.form.get("username_give")
    exists = bool(db.users.find_one({"username": username_receive}))
    return jsonify({"result": "success", "exists": exists})


@app.route("/update_profile", methods=["POST"])
def update_profile():
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        username = payload.get("username")
        name_receive = request.form.get("name_give")
        about_receive = request.form.get("about_give")

        new_doc = {"profile_name": name_receive, "profile_info": about_receive}

        if "file_give" in request.files:
            file = request.files.get("file_give")
            filename = secure_filename(file.filename)
            extension = filename.split(".")[-1]
            file_path = f"img/profile/{username}.{extension}"
            file.save("./static/" + file_path)

            new_doc["profile_pic"] = filename
            new_doc["profile_pic_real"] = file_path
        db.users.update_one({"username": username}, {"$set": new_doc})
        return jsonify(
            {
                "result": "success",
                "msg": "Your profile has been updated",
            }
        )
    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("home"))


@app.route("/posting", methods=["POST"])
def posting():
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        print(payload)
        user_info = db.users.find_one({"username": payload.get("username")})
        comment_receive = request.form.get("comment_give")
        date_receive = request.form.get("date_give")
        print(user_info)
        doc = {
            "username": user_info.get("username"),
            "profile_name": user_info.get("profile_name"),
            "profile_pic_real": user_info.get("profile_pic_real"),
            "comment": comment_receive,
            "date": date_receive,
        }
        db.posts.insert_one(doc)

        return jsonify({"result": "success", "msg": "Posting Successfull"})
    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("home"))


@app.route("/get_posts", methods=["GET"])
def get_posts():
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        username_receive = request.args.get("username_give")
        if username_receive == "":
            posts = list(db.posts.find({}).sort("date", -1).limit(20))
        else:
            posts = list(
                db.posts.find({"username": username_receive}).sort("date", -1).limit(20)
            )
        for post in posts:
            post["_id"] = str(post["_id"])
            # heart
            post["count_heart"] = db.likes.count_documents(
                {"post_id": post["_id"], "type": "heart"}
            )

            post["heart_by_me"] = bool(
                db.likes.find_one(
                    {
                        "post_id": post["_id"],
                        "type": "heart",
                        "username": payload.get("id"),
                    }
                )
            )

            # star
            post["count_star"] = db.likes.count_documents(
                {"post_id": post["_id"], "type": "star"}
            )

            post["star_by_me"] = bool(
                db.likes.find_one(
                    {
                        "post_id": post["_id"],
                        "type": "star",
                        "username": payload.get("id"),
                    }
                )
            )

            # thumbs
            post["count_thumbsup"] = db.likes.count_documents(
                {"post_id": post["_id"], "type": "thumbsup"}
            )

            post["thumbsup_by_me"] = bool(
                db.likes.find_one(
                    {
                        "post_id": post["_id"],
                        "type": "thumbsup",
                        "username": payload.get("id"),
                    }
                )
            )

        return jsonify(
            {
                "result": "success",
                "msg": "Successfully fetched all posts",
                "posts": posts,
            }
        )
    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("home"))


@app.route("/update_like", methods=["POST"])
def update_like():
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        user_info = db.users.find_one({"username": payload.get("username")})
        post_id_receiver = request.form.get("post_id_give")
        type_receiver = request.form.get("type_give")
        action_receiver = request.form.get("action_give")
        doc = {
            "post_id": post_id_receiver,
            "username": user_info.get("username"),
            "type": type_receiver,
        }
        if action_receiver == "like":
            db.likes.insert_one(doc)
        else:
            db.likes.delete_one(doc)
        count = db.likes.count_documents(
            {
                "post_id": post_id_receiver,
                "type": type_receiver,
            }
        )
        return jsonify(
            {
                "result": "success",
                "msg": "Updated!",
                "count": count,
            }
        )
    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("home"))


@app.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@app.route("/secret", methods=["GET"])
def secret():
    token_receive = request.cookies.get(TOKEN_KEY)
    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=["HS256"])
        user_info = db.users.find_one({"username": payload.get("username")})
        print(user_info)
        return render_template("secret.html", user_info=user_info)
    except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
        return redirect(url_for("home"))


if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=True)
