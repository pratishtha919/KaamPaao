// KaamPaao — auth page interactions. Phone-OTP login and the inline phone
// verification on signup require JS.

(function () {
    'use strict';

    const $ = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

    function csrfToken(form) {
        const i = form ? form.querySelector('input[name="csrf_token"]') : null;
        return i ? i.value : '';
    }

    function toE164(localDigits) {
        const digits = (localDigits || '').replace(/\D+/g, '');
        return digits.length === 10 ? '+91' + digits : '';
    }

    // ---------------------------------------------------------------------
    // OTP API helpers
    // ---------------------------------------------------------------------
    function apiOtp(path, body, csrf) {
        return fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf || '',
                'Accept': 'application/json',
            },
            body: JSON.stringify(body),
        }).then(r => r.json().then(data => ({ status: r.status, data })));
    }

    function showDevBanner(field, code) {
        if (!code) return;
        let banner = field.querySelector('.dev-otp-banner');
        if (!banner) {
            banner = document.createElement('div');
            banner.className = 'dev-otp-banner';
            banner.setAttribute('role', 'status');
            field.appendChild(banner);
        }
        banner.innerHTML = 'Dev mode — your OTP is <code>' + code + '</code>';
    }
    function clearDevBanner(field) {
        const banner = field.querySelector('.dev-otp-banner');
        if (banner) banner.remove();
    }
    function setStatus(block, msg, kind) {
        const el = block.querySelector('[data-otp-status]');
        if (!el) return;
        el.textContent = msg || '';
        el.className = 'field-help' + (kind === 'error' ? ' field-error' : '');
    }

    // ---------------------------------------------------------------------
    // Phone-field plumbing (login & signup share the same shape)
    // ---------------------------------------------------------------------
    function wirePhoneField(scope) {
        const field = scope.querySelector('[data-phone-field]');
        if (!field) return null;
        const local = field.querySelector('input[name="phone_local"]');
        const e164 = field.querySelector('[data-phone-e164]');

        function sync() {
            const v = toE164(local.value);
            e164.value = v;
            return v;
        }
        local.addEventListener('input', () => {
            local.value = local.value.replace(/\D+/g, '').slice(0, 10);
            sync();
        });
        sync();
        return { field, local, e164, sync };
    }

    // ---------------------------------------------------------------------
    // Signup: inline phone verification
    // ---------------------------------------------------------------------
    const signupForm = $('form[data-form="signup"]');
    if (signupForm) {
        const pf = wirePhoneField(signupForm);
        const verifyBtn = signupForm.querySelector('.phone-verify-btn');
        const otpBlock = signupForm.querySelector('[data-otp-block]');
        const otpInput = $('#signup-otp');
        const verifiedPanel = signupForm.querySelector('[data-phone-verified]');
        const submitBtn = signupForm.querySelector('[data-needs-phone-verified]');

        let verifiedPhone = null;

        function refreshSubmitState() {
            if (!submitBtn) return;
            submitBtn.disabled = !verifiedPhone || verifiedPhone !== pf.sync();
        }

        function showPhoneError(msg) {
            const el = pf.field.querySelector('[data-phone-error]');
            if (el) { el.textContent = msg; el.hidden = false; }
            pf.field.classList.add('has-error');
        }
        function clearPhoneError() {
            const el = pf.field.querySelector('[data-phone-error]');
            if (el) { el.textContent = ''; el.hidden = true; }
            pf.field.classList.remove('has-error');
        }

        function resetVerification() {
            verifiedPhone = null;
            if (verifiedPanel) verifiedPanel.hidden = true;
            if (otpBlock) { otpBlock.hidden = true; clearDevBanner(pf.field); setStatus(otpBlock, '', null); }
            if (verifyBtn) { verifyBtn.disabled = false; verifyBtn.textContent = 'Verify'; }
            clearPhoneError();
            refreshSubmitState();
        }

        pf.local.addEventListener('input', () => {
            clearPhoneError();
            if (verifiedPhone && verifiedPhone !== pf.sync()) resetVerification();
            refreshSubmitState();
        });

        async function sendOtp() {
            const phone = pf.sync();
            clearPhoneError();
            if (!phone) {
                showPhoneError('Enter a valid 10-digit Indian mobile number.');
                pf.local.focus();
                return;
            }
            verifyBtn.disabled = true;
            verifyBtn.textContent = 'Sending…';
            try {
                const r = await apiOtp('/api/otp/request',
                    { phone, purpose: 'signup_verify' }, csrfToken(signupForm));
                if (!r.data.ok) {
                    showPhoneError(r.data.message || 'Could not send code.');
                    verifyBtn.disabled = false;
                    verifyBtn.textContent = 'Verify';
                    pf.local.focus();
                    return;
                }
                otpBlock.hidden = false;
                setStatus(otpBlock, 'Code sent to +91 ' + pf.local.value + '. Expires in 5 min.', null);
                showDevBanner(pf.field, r.data.dev_code);
                verifyBtn.textContent = 'Resend';
                verifyBtn.disabled = false;
                if (otpInput) { otpInput.value = ''; otpInput.focus(); }
            } catch (err) {
                showPhoneError('Network error. Try again.');
                verifyBtn.disabled = false;
                verifyBtn.textContent = 'Verify';
            }
        }

        async function verifyOtp() {
            const phone = pf.sync();
            const code = (otpInput.value || '').trim();
            if (!phone || code.length !== 6) {
                setStatus(otpBlock, 'Enter the 6-digit code.', 'error');
                return;
            }
            setStatus(otpBlock, 'Checking…', null);
            try {
                const r = await apiOtp('/api/otp/verify',
                    { phone, purpose: 'signup_verify', code }, csrfToken(signupForm));
                if (!r.data.ok) {
                    setStatus(otpBlock, r.data.message || 'Incorrect code.', 'error');
                    return;
                }
                verifiedPhone = phone;
                pf.field.classList.remove('has-error');
                otpBlock.hidden = true;
                clearDevBanner(pf.field);
                if (verifiedPanel) verifiedPanel.hidden = false;
                refreshSubmitState();
            } catch (err) {
                setStatus(otpBlock, 'Network error. Try again.', 'error');
            }
        }

        if (verifyBtn) verifyBtn.addEventListener('click', sendOtp);
        const verifyCodeBtn = signupForm.querySelector('[data-verify-otp="signup_verify"]');
        if (verifyCodeBtn) verifyCodeBtn.addEventListener('click', verifyOtp);
        if (otpInput) {
            otpInput.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); verifyOtp(); }
            });
            otpInput.addEventListener('input', () => {
                otpInput.value = otpInput.value.replace(/\D+/g, '').slice(0, 6);
            });
        }
        const resendBtn = signupForm.querySelector('[data-resend-otp="signup_verify"]');
        if (resendBtn) resendBtn.addEventListener('click', e => { e.preventDefault(); sendOtp(); });

        const changeBtn = signupForm.querySelector('[data-change-phone]');
        if (changeBtn) changeBtn.addEventListener('click', () => {
            resetVerification();
            pf.local.focus();
        });

        // Block submit if phone isn't verified.
        signupForm.addEventListener('submit', e => {
            const phone = pf.sync();
            if (!phone || phone !== verifiedPhone) {
                e.preventDefault();
                if (!phone) pf.field.classList.add('has-error');
                setStatus(otpBlock, 'Please verify your phone number first.', 'error');
                otpBlock.hidden = false;
                pf.local.focus();
            }
        });

        refreshSubmitState();
    }

    // ---------------------------------------------------------------------
    // Login: phone+OTP form
    // ---------------------------------------------------------------------
    const phoneLoginForm = $('form[data-form="login-otp"]');
    if (phoneLoginForm) {
        const pf = wirePhoneField(phoneLoginForm);
        const sendBtn = phoneLoginForm.querySelector('[data-send-otp="login"]');
        const otpBlock = phoneLoginForm.querySelector('[data-otp-block]');
        const otpInput = $('#login-otp');

        async function sendOtp() {
            const phone = pf.sync();
            if (!phone) {
                pf.field.classList.add('has-error');
                pf.local.focus();
                return;
            }
            sendBtn.disabled = true;
            sendBtn.textContent = 'Sending…';
            try {
                const r = await apiOtp('/api/otp/request',
                    { phone, purpose: 'login' }, csrfToken(phoneLoginForm));
                if (!r.data.ok) {
                    setStatus(otpBlock || pf.field, r.data.message || 'Could not send code.', 'error');
                    sendBtn.disabled = false;
                    sendBtn.textContent = 'Send OTP';
                    if (otpBlock) otpBlock.hidden = false;
                    return;
                }
                otpBlock.hidden = false;
                setStatus(otpBlock, 'Code sent to +91 ' + pf.local.value + '. Expires in 5 min.', null);
                showDevBanner(pf.field, r.data.dev_code);
                sendBtn.textContent = 'Resend OTP';
                sendBtn.disabled = false;
                if (otpInput) { otpInput.value = ''; otpInput.focus(); }
            } catch (err) {
                setStatus(otpBlock || pf.field, 'Network error. Try again.', 'error');
                sendBtn.disabled = false;
                sendBtn.textContent = 'Send OTP';
            }
        }

        if (sendBtn) sendBtn.addEventListener('click', sendOtp);
        const resend = phoneLoginForm.querySelector('[data-resend-otp="login"]');
        if (resend) resend.addEventListener('click', e => { e.preventDefault(); sendOtp(); });

        if (otpInput) {
            otpInput.addEventListener('input', () => {
                otpInput.value = otpInput.value.replace(/\D+/g, '').slice(0, 6);
            });
        }

        phoneLoginForm.addEventListener('submit', e => {
            const phone = pf.sync();
            if (!phone) {
                e.preventDefault();
                pf.field.classList.add('has-error');
                pf.local.focus();
            }
        });
    }

    // ---------------------------------------------------------------------
    // Submit spinner (all auth forms)
    // ---------------------------------------------------------------------
    $$('form.auth-form').forEach(form => {
        form.addEventListener('submit', () => {
            const btn = form.querySelector('[data-submit]');
            if (!btn || btn.disabled) return;
            const labelEl = btn.querySelector('.btn-label');
            const original = labelEl ? labelEl.textContent : btn.textContent;
            const which = form.dataset.form;
            const busyText =
                which === 'signup' ? 'Creating account…'
                : which === 'login-otp' ? 'Logging in…'
                : 'Logging in…';
            btn.disabled = true;
            btn.setAttribute('aria-busy', 'true');
            btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>'
                + '<span class="btn-label">' + busyText + '</span>';
            setTimeout(() => {
                if (!form.checkValidity()) {
                    btn.disabled = false;
                    btn.removeAttribute('aria-busy');
                    btn.innerHTML = '<span class="btn-label">' + original + '</span>';
                }
            }, 0);
        });
    });

    // ---------------------------------------------------------------------
    // Auto-focus first empty visible required field on load
    // ---------------------------------------------------------------------
    const card = $('.form-card');
    if (card) {
        const first = card.querySelector('input[required]:not([disabled]):not([hidden])');
        if (first && !first.value && first.offsetParent !== null) first.focus();
    }
})();
