from expense_tracker import create_app

app = create_app()

if __name__ == "__main__":
    # Use 0.0.0.0 in production or inside containers.
    app.run(host="0.0.0.0", port=5000, debug=True)
