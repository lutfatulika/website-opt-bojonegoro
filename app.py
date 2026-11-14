
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from functools import wraps
from pathlib import Path
import json
import joblib
import pandas as pd
import mysql.connector
from mysql.connector import Error

# =====================================
# KONFIGURASI APLIKASI FLASK
# =====================================

app = Flask(__name__)
app.secret_key = "opt-bojonegoro-secret-key-2026"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "OPTBojonegoro2026"

# =====================================
# KONFIGURASI DATABASE MYSQL
# =====================================

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "opt_bojonegoro"
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


# =====================================
# MEMUAT MODEL RANDOM FOREST
# =====================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = BASE_DIR / "models" / "random_forest_opt_final.joblib"
METADATA_PATH = BASE_DIR / "models" / "metadata_model.json"

model = None
model_error = None
metadata_model = {}

try:
    model = joblib.load(MODEL_PATH)

    if METADATA_PATH.exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as file:
            metadata_model = json.load(file)

    print("MODEL RANDOM FOREST BERHASIL DIMUAT")

except Exception as e:
    model_error = str(e)
    print("GAGAL MEMUAT MODEL:", model_error)


# =====================================
# PEMERIKSAAN LOGIN
# =====================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function


# =====================================
# HALAMAN LOGIN
# =====================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("admin_logged_in"):
        return redirect(url_for("beranda"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username dan password tidak boleh kosong.", "error")

        elif username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username

            return redirect(url_for("beranda"))

        else:
            flash("Username atau password salah.", "error")

    return render_template("login.html")


# =====================================
# DASHBOARD
# =====================================

@app.route("/")
@login_required
def beranda():
    return render_template("index.html")


# =====================================
# DATA HISTORIS
# =====================================

@app.route("/data-historis")
@login_required
def data_historis():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                kecamatan,
                komoditas,
                jenis_opt,
                tahun,
                luas_serangan
            FROM data_historis_opt
            ORDER BY tahun DESC, kecamatan ASC, jenis_opt ASC
        """)

        data = cursor.fetchall()

        return render_template(
            "data_historis.html",
            data=data,
            pesan_error=None
        )

    except Error as e:

        print("Kesalahan database:", e)

        return render_template(
            "data_historis.html",
            data=[],
            pesan_error=(
                "Data historis belum dapat dimuat. "
                "Periksa koneksi database."
            )
        )

    finally:

        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


# =====================================
# DATA OPT
# =====================================

@app.route("/data-opt")
@login_required
def data_opt():

    connection = None
    cursor = None

    ringkasan = {
        "total_catatan": 0,
        "jumlah_kecamatan": 0,
        "jumlah_jenis_opt": 0,
        "tahun_awal": None,
        "tahun_akhir": None,
        "komoditas": "Padi"
    }

    opts = []
    pesan_error = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                COUNT(*) AS total_catatan,
                COUNT(DISTINCT kecamatan) AS jumlah_kecamatan,
                COUNT(DISTINCT jenis_opt) AS jumlah_jenis_opt,
                MIN(tahun) AS tahun_awal,
                MAX(tahun) AS tahun_akhir,
                GROUP_CONCAT(
                    DISTINCT komoditas
                    ORDER BY komoditas
                    SEPARATOR ', '
                ) AS komoditas
            FROM data_historis_opt
        """)

        hasil_ringkasan = cursor.fetchone()

        if hasil_ringkasan is not None:
            ringkasan = hasil_ringkasan

        cursor.execute("""
            SELECT
                jenis_opt,
                COUNT(*) AS jumlah_catatan,
                COUNT(DISTINCT kecamatan) AS jumlah_kecamatan,
                MIN(tahun) AS tahun_awal,
                MAX(tahun) AS tahun_akhir
            FROM data_historis_opt
            WHERE jenis_opt IS NOT NULL
              AND TRIM(jenis_opt) <> ''
            GROUP BY jenis_opt
            ORDER BY jenis_opt
        """)

        opts = cursor.fetchall()

    except Error as e:

        print("Kesalahan database Data OPT:", e)

        pesan_error = (
            "Data OPT belum dapat dimuat. "
            "Periksa koneksi database."
        )

    finally:

        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return render_template(
        "data_opt.html",
        ringkasan=ringkasan,
        opts=opts,
        pesan_error=pesan_error
    )


# =====================================
# HALAMAN PREDIKSI OPT
# =====================================

@app.route("/prediksi")
@login_required
def prediksi():

    connection = None
    cursor = None

    kecamatan_list = []
    jenis_opt_list = []
    pesan_error = model_error

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT DISTINCT kecamatan
            FROM data_historis_opt
            WHERE kecamatan IS NOT NULL
              AND TRIM(kecamatan) <> ''
            ORDER BY kecamatan ASC
        """)

        kecamatan_list = cursor.fetchall()

        cursor.execute("""
            SELECT DISTINCT jenis_opt
            FROM data_historis_opt
            WHERE jenis_opt IS NOT NULL
              AND TRIM(jenis_opt) <> ''
            ORDER BY jenis_opt ASC
        """)

        jenis_opt_list = cursor.fetchall()

    except Error as e:

        print("Kesalahan database halaman Prediksi:", e)

        pesan_error = (
            "Pilihan prediksi belum dapat dimuat. "
            "Periksa koneksi database."
        )

    finally:

        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    return render_template(
        "prediksi.html",
        kecamatan_list=kecamatan_list,
        jenis_opt_list=jenis_opt_list,
        pesan_error=pesan_error
    )


# =====================================
# API PREDIKSI RANDOM FOREST
# =====================================

@app.route("/api/prediksi", methods=["POST"])
@login_required
def api_prediksi():

    if model is None:
        return jsonify({
            "success": False,
            "message": "Model belum berhasil dimuat: " + str(model_error)
        }), 500

    payload = request.get_json(silent=True) or request.form

    kecamatan = str(payload.get("kecamatan", "")).strip()
    jenis_opt = str(payload.get("jenis_opt", "")).strip()

    try:
        tahun_diminta = int(payload.get("tahun", 2026))

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Tahun prediksi tidak valid."
        }), 400

    if not kecamatan or not jenis_opt:
        return jsonify({
            "success": False,
            "message": "Pilih kecamatan dan jenis OPT."
        }), 400

    if tahun_diminta < 2026 or tahun_diminta > 2030:
        return jsonify({
            "success": False,
            "message": "Tahun prediksi tersedia 2026 sampai 2030."
        }), 400

    # Memeriksa kategori yang dikenali model
    try:
        encoder = (
            model.named_steps["preprocessing"]
            .named_transformers_["kategori"]
        )

        kategori_kecamatan = [
            str(x) for x in encoder.categories_[0]
        ]

        kategori_opt = [
            str(x) for x in encoder.categories_[1]
        ]

        if kecamatan not in kategori_kecamatan:
            return jsonify({
                "success": False,
                "message": "Nama kecamatan tidak dikenali model."
            }), 400

        if jenis_opt not in kategori_opt:
            return jsonify({
                "success": False,
                "message": "Nama jenis OPT tidak dikenali model."
            }), 400

    except Exception as e:

        print("Kesalahan pemeriksaan kategori:", e)

        return jsonify({
            "success": False,
            "message": "Gagal memeriksa kategori model."
        }), 500

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Mengambil data aktual tahun 2025
        cursor.execute("""
            SELECT tahun, luas_serangan
            FROM data_historis_opt
            WHERE kecamatan = %s
              AND jenis_opt = %s
              AND tahun = 2025
            LIMIT 1
        """, (kecamatan, jenis_opt))

        row = cursor.fetchone()

        if row is None or row["luas_serangan"] is None:
            return jsonify({
                "success": False,
                "message": (
                    "Data aktual tahun 2025 tidak ditemukan "
                    "untuk kombinasi kecamatan dan jenis OPT tersebut."
                )
            }), 404

        luas_lag = float(row["luas_serangan"])

        hasil_diminta = None
        jejak_prediksi = []

        # Menghitung seluruh prediksi 2026–2030
        for tahun in range(2026, 2031):

            input_model = pd.DataFrame([{
                "Kecamatan": kecamatan,
                "Jenis_OPT": jenis_opt,
                "Tahun": tahun,
                "Luas_Serangan_Tahun_Sebelumnya": luas_lag
            }], columns=[
                "Kecamatan",
                "Jenis_OPT",
                "Tahun",
                "Luas_Serangan_Tahun_Sebelumnya"
            ])

            nilai_prediksi = float(
                model.predict(input_model)[0]
            )

            # Luas serangan tidak boleh negatif
            nilai_prediksi = max(0.0, nilai_prediksi)

            jejak_prediksi.append({
                "tahun": tahun,
                "luas_serangan_tahun_sebelumnya": round(luas_lag, 4),
                "prediksi": round(nilai_prediksi, 4)
            })

            if tahun == tahun_diminta:
                hasil_diminta = nilai_prediksi

            # Hasil prediksi menjadi lag tahun berikutnya
            luas_lag = nilai_prediksi

        hasil_tahun_dipilih = next(
            item for item in jejak_prediksi
            if item["tahun"] == tahun_diminta
        )

        jumlah_pohon = len(
            model.named_steps["random_forest"].estimators_
        )

        return jsonify({
            "success": True,
            "kecamatan": kecamatan,
            "jenis_opt": jenis_opt,
            "tahun": tahun_diminta,

            "luas_serangan_tahun_sebelumnya":
                hasil_tahun_dipilih[
                    "luas_serangan_tahun_sebelumnya"
                ],

            "prediksi": round(hasil_diminta, 4),
            "satuan": "Ha",
            "metode": "Random Forest Regression",
            "jumlah_pohon": jumlah_pohon,

            "catatan": (
                "Prediksi 2026 menggunakan data aktual 2025. "
                "Prediksi 2027–2030 menggunakan hasil prediksi "
                "tahun sebelumnya sebagai fitur lag."
            ),

            "data_aktual_2025": round(
                float(row["luas_serangan"]), 4
            ),

            "rangkaian_prediksi": jejak_prediksi
        })

    except Error as e:

        print("Kesalahan database saat prediksi:", e)

        return jsonify({
            "success": False,
            "message": (
                "Kesalahan saat mengambil data historis dari database."
            )
        }), 500

    except Exception as e:

        print("Kesalahan proses prediksi:", e)

        return jsonify({
            "success": False,
            "message": (
                "Prediksi gagal diproses. Periksa terminal Flask."
            )
        }), 500

    finally:

        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


# =====================================
# HALAMAN EVALUASI MODEL
# =====================================

@app.route("/evaluasi")
@login_required
def evaluasi():
    return render_template("evaluasi.html")


# =====================================
# HALAMAN PROFIL ADMIN
# =====================================

@app.route("/profil-admin")
@login_required
def profil_admin():
    return render_template("profil_admin.html")


# =====================================
# LOGOUT
# =====================================

@app.route("/logout")
def logout():

    session.clear()

    flash("Kamu berhasil keluar dari sistem.", "success")

    return redirect(url_for("login"))


# =====================================
# MENJALANKAN FLASK
# =====================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
