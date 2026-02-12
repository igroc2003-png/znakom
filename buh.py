from flask import Flask, request
import hashlib
from config import ROBO_PASS2
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

DB_PATH = "database.db"


def add_vip(user_id, days):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверяем есть ли пользователь
    cursor.execute("SELECT vip_until FROM profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    current_vip = row[0]

    now_ts = int(datetime.now().timestamp())

    # Если VIP уже есть — продлеваем
    if current_vip and current_vip > now_ts:
        new_vip = current_vip + days * 86400
    else:
        new_vip = now_ts + days * 86400

    cursor.execute(
        "UPDATE profiles SET vip_until = ? WHERE user_id = ?",
        (new_vip, user_id)
    )

    conn.commit()
    conn.close()
    return True


@app.route("/robokassa_result", methods=["POST"])
def result():
    out_summ = request.form.get("OutSum")
    inv_id = request.form.get("InvId")
    signature = request.form.get("SignatureValue", "").upper()

    if not out_summ or not inv_id:
        return "bad request"

    # Проверяем подпись
    my_crc = hashlib.md5(
        f"{out_summ}:{inv_id}:{ROBO_PASS2}".encode()
    ).hexdigest().upper()

    if my_crc != signature:
        return "bad sign"

    try:
        user_id, days = inv_id.split("_")
        user_id = str(user_id)
        days = int(days)
    except:
        return "bad invoice"

    success = add_vip(user_id, days)

    if not success:
        return "user not found"

    return f"OK{inv_id}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
