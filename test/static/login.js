// Show/Hide password
function togglePassword() {
    let pass = document.getElementById("password");

    if (pass.type === "password") {
        pass.type = "text";
    } else {
        pass.type = "password";
    }
}


// Validate login form
function validateLogin() {

    let user = document.getElementById("userid").value;
    let pass = document.getElementById("password").value;

    let userError = document.getElementById("userError");
    let passError = document.getElementById("passError");

    userError.innerText = "";
    passError.innerText = "";

    let valid = true;

    // USER ID validation
    if (user.length < 3) {
        userError.innerText = "User ID must be at least 3 characters";
        valid = false;
    }

    // PASSWORD validation
    if (pass.length < 6) {
        passError.innerText = "Password must be at least 6 characters";
        valid = false;
    }

    // Strong password check
    let pattern = /^(?=.*[A-Z])(?=.*[0-9])/;

    if (!pattern.test(pass)) {
        passError.innerText = "Password must contain 1 capital letter and 1 number";
        valid = false;
    }

    return valid;
}