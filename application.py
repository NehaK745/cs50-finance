import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

 Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
      SELECT symbol, SUM(shares) as totalShares
      FROM transactions
      WHERE user_id = :user_id
      GROUP BY symbol
      HAVING totalShares > 0;
    """, user_id=session["user_id"])
    holding = []
    total = 0
    for row in rows:
        stock = lookup(row["symbol"])
        holding.append({
            "symbol": stock["symbol"],
            "name":   stock["name"],
            "shares": row["totalShares"],
            "price": usd(stock["price"]),
            "total": usd(stock["price"] * row["totalShares"])
        })
        total += stock["price"] * row["totalShares"]
    rows = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id = session["user_id"])
    cash = rows[0]["cash"]
    total += cash
    
    return render_template("index.html", holding=holding, cash=usd(cash), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)
        elif not request.form.get("shares"):
            return apology("must provide shares", 403)
        elif not request.form.get("shares").isdigit():
            return apology("Invalid no of shares")
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid symbol")
        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]["cash"]
        updated_cash = cash - shares * stock['price']
        if updated_cash < 0:
            return apology("can't afford")
        db.execute("UPDATE users SET cash=:updated_cash WHERE id=:id",
                   updated_cash=updated_cash,
                   id=session["user_id"])
        db.execute("""INSERT INTO transactions(user_id, symbol, shares, price) 
                    VALUES(:user_id, :symbol,:shares,:price)""",
                    user_id = session["user_id"],symbol = stock["symbol"], shares = shares, price = stock["price"]
                    )
        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")
    
   

  


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute(""" 
                SELECT symbol, shares, price, transacted
                FROM transactions 
                WHERE user_id =:user_id
                """, user_id=session["user_id"])
    for i in range(len(transactions)):
        transactions[i]["price"] = usd(transactions[i]["price"])
    return render_template("history.html", transactions = transactions)
    return apology("TODO")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        input_symbol = request.form.get("symbol")
        if not input_symbol:
            return apology("must provide symbol", 403)
        elif not lookup(input_symbol):
            return apology("stock not found", 403)

        quote = lookup(input_symbol)

        quote["price"] = usd(quote["price"])

        return render_template("quoted.html", quote = quote)

    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        user_name = request.form.get("username")
        user_pass = request.form.get("password")
        confirmation_pass = request.form.get("confirmation")

        if not user_name:
            return apology("must provide username", 403)
        elif not user_pass:
            return apology("must provide password", 403)
        elif not confirmation_pass:
            return apology("must provide confirm password")
        elif not user_pass == confirmation_pass:
            return apology("password doesn't match")
        username = db.execute("SELECT username FROM users WHERE username = :username",
                          username = user_name)
        if len(username) == 1:
            return apology("sorry, username is already taken")

        else:
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                            username = user_name,
                            password = generate_password_hash(user_pass, method="pbkdf2:sha256", salt_length=8))
        if new_user:
            session["user_id"] = new_user
        flash(f"Registered as {user_name}")
        return redirect("/")
    else:
        return render_template("register.html")

@app.route("/add_amount", methods=["GET", "POST"])
@login_required
def add_amount():
    if request.method == "POST":
        db.execute("""UPDATE users SET cash = cash + :amount 
        WHERE id=:user_id
        """, 
        amount = request.form.get("cash"), 
        user_id=session["user_id"])
        flash("Added Cash!")
        return redirect("/")
    else:
        return render_template("add_amount.html")
        




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    
    """Sell shares of stock"""
    if request.method == "POST":
        print(request.form.get("symbol"))
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)
        elif not request.form.get("shares"):
            return apology("must provide shares", 403)
        elif not request.form.get("shares").isdigit():
            return apology("Invalid no of shares")
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid symbol")
            
        rows = db.execute("""
              SELECT symbol, SUM(shares) as totalShares
              FROM transactions
              WHERE user_id =:user_id
              GROUP BY symbol
              HAVING totalShares > 0;
              """, user_id=session["user_id"])
        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["totalShares"]:
                    return apology("too many shares")
        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]["cash"]
        updated_cash = cash + shares * stock['price']
        db.execute("UPDATE users SET cash=:updated_cash WHERE id=:id",
                   updated_cash=updated_cash,
                   id=session["user_id"])
        db.execute("""INSERT INTO transactions(user_id, symbol, shares, price) 
                    VALUES(:user_id, :symbol,:shares,:price)
                    """,
                    user_id = session["user_id"],
                    symbol = stock["symbol"], 
                    shares = -1 * shares, 
                    price = stock["price"]
                    )
        flash("SOLD!")
        return redirect("/")
    else:
        rows = db.execute(""" 
        SELECT symbol FROM transactions 
        WHERE user_id =:user_id 
        GROUP BY symbol HAVING SUM(shares) > 0;
        """, user_id = session["user_id"])
        return render_template("sell.html", symbols= [row["symbol"] for row in rows ])
        

     


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
