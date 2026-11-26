"""
Email utilities for Eacyclic.

Supports Resend HTTP API (recommended on Render free tier where outbound SMTP
ports 587/465 are blocked) with automatic fallback to Django SMTP / Console.
All user-facing emails dispatch in background daemon threads by default so API
requests return immediately.
"""

import html
import threading
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def _format_currency(amount):
    try:
        return f"₹{round(float(amount or 0)):,}"
    except (TypeError, ValueError):
        return f"₹{amount or 0}"


def send_eacyclic_email(to_emails, subject, plain_message, html_message, tag="EMAIL"):
    """
    Send a transactional email via Resend HTTP API or Django's configured
    email backend. Returns (success: bool, error: str | None).
    """
    recipients = [e.strip() for e in (to_emails or []) if e and str(e).strip()]
    if not recipients:
        return False, "No recipient email provided."

    resend_api_key = getattr(settings, 'RESEND_API_KEY', '').strip()
    backend_used = getattr(settings, 'EMAIL_BACKEND', '')
    is_test_backend = 'locmem' in backend_used or 'dummy' in backend_used

    if resend_api_key and not is_test_backend:
        try:
            import resend
            resend.api_key = resend_api_key
            from_addr = getattr(settings, 'RESEND_FROM_EMAIL', 'Eacyclic <noreply@eacyclic.com>')
            print(f"[{tag} BG] Sending via Resend API to {recipients} from {from_addr}")
            res = resend.Emails.send({
                "from": from_addr,
                "to": recipients,
                "subject": subject,
                "html": html_message,
                "text": plain_message,
            })
            print(f"[{tag} BG] Resend response: {res}")
            return True, None
        except Exception as exc:
            print(f"[{tag} BG ERROR] Resend failed: {exc}")
            # Fall through to Django mail backend only if SMTP credentials exist
            if 'smtp' not in backend_used:
                return False, str(exc)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@eacyclic.com'
    try:
        print(f"[{tag} BG] Sending via Django backend ({backend_used}) to {recipients}")
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False,
        )
        print(f"[{tag} BG] Successfully sent to {recipients}")
        return True, None
    except Exception as exc:
        print(f"[{tag} BG ERROR] Django send_mail failed: {exc}")
        return False, str(exc)


def dispatch_email_async(to_emails, subject, plain_message, html_message, tag="EMAIL", on_failure=None):
    """
    Dispatch an email asynchronously in a background daemon thread (or
    synchronously when EMAIL_SYNC_FOR_TESTS=True for deterministic tests).
    """
    def _worker():
        sent, err = send_eacyclic_email(to_emails, subject, plain_message, html_message, tag=tag)
        if not sent and on_failure:
            on_failure(err)

    if getattr(settings, 'EMAIL_SYNC_FOR_TESTS', False):
        _worker()
    else:
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()


def generate_otp_html_email(otp_code):
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Verification Code</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 30px 15px; color: #1e293b;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01); border: 1px solid #e2e8f0;">
        <div style="background: linear-gradient(135deg, #134e35 0%, #0e3a27 100%); padding: 34px 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 28px; font-weight: 900; letter-spacing: -0.5px; margin-bottom: 4px;">Eacyclic</div>
            <div style="font-size: 12px; font-weight: 600; color: rgba(255, 255, 255, 0.85); text-transform: uppercase; letter-spacing: 1.5px;">Secure Sign In</div>
        </div>
        <div style="padding: 36px 32px; text-align: center;">
            <div style="font-size: 20px; font-weight: 800; color: #0f172a; margin-bottom: 8px;">Your Authentication Code</div>
            <div style="font-size: 14px; color: #64748b; line-height: 1.6; margin-bottom: 28px;">
                Use the verification code below to log in to your Eacyclic account.
            </div>
            <div style="background: #fff7ed; border: 1.5px solid #ffedd5; border-radius: 16px; padding: 14px 12px; margin: 0 auto 28px auto; text-align: center;">
                <div style="font-size: 28px; font-weight: 900; letter-spacing: 12px; color: #000000; font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, monospace; margin-left: 12px;">{html.escape(str(otp_code))}</div>
                <div style="display: inline-block; background-color: #ffedd5; color: #c2410c; font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 20px; margin-top: 14px;">Valid for 5 minutes</div>
            </div>
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 12px; text-align: left; font-size: 13px; color: #475569; line-height: 1.5;">
                <strong style="color: #0f172a;">Security Notice:</strong> If you did not request this code, please ignore this email. Do not share this code with anyone.
            </div>
        </div>
        <div style="background-color: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9;">
            &copy; {timezone.now().year} Eacyclic. All rights reserved.
        </div>
    </div>
</body>
</html>"""


def dispatch_otp_email_async(email, otp_code):
    """Send the login OTP email asynchronously."""
    subject = 'Your Verification Code - Eacyclic'
    plain_message = (
        f'Hello,\n\nYour OTP verification code is: {otp_code}\n\n'
        'This code is valid for 5 minutes. Do not share this code with anyone.'
    )
    html_message = generate_otp_html_email(otp_code)

    def _on_fail(err):
        print("=================================================")
        print(f"[OTP FALLBACK] EMAIL FAILED — OTP FOR {email}: {otp_code}")
        print(f"[OTP FALLBACK] Error: {err}")
        print("=================================================")

    print(f"[OTP DISPATCH] Generated OTP for {email}: {otp_code} (Valid for 5 mins)")
    dispatch_email_async([email], subject, plain_message, html_message, tag="OTP EMAIL", on_failure=_on_fail)


def generate_order_confirmation_html_email(order):
    """Build a mobile-friendly HTML order receipt and tracking email."""
    site_url = getattr(settings, 'SITE_URL', 'https://eacyclic.com')
    track_url = f"{site_url}/order-status/{order.id}"
    shop_url = f"{site_url}/product"

    delivery = getattr(order, 'delivery', None)
    tracking_number = delivery.tracking_number if delivery and delivery.tracking_number else "Generating shortly"
    est_date = (
        delivery.estimated_delivery.strftime('%a, %d %b %Y')
        if delivery and delivery.estimated_delivery
        else (timezone.now() + timedelta(days=4)).strftime('%a, %d %b %Y')
    )

    items_html = []
    for item in order.items.all():
        variant_parts = []
        if item.selected_size:
            variant_parts.append(f"Size: {html.escape(str(item.selected_size))}")
        if item.selected_color:
            variant_parts.append(f"Color: {html.escape(str(item.selected_color))}")
        variant_line = (
            f"<div style='font-size: 12px; color: #64748b; margin-top: 2px;'>{' • '.join(variant_parts)}</div>"
            if variant_parts
            else ""
        )
        line_total = _format_currency(float(item.price or 0) * int(item.quantity or 1))
        items_html.append(f"""
        <tr>
            <td style="padding: 12px 0; border-bottom: 1px solid #f1f5f9;">
                <div style="font-size: 14px; font-weight: 700; color: #0f172a;">{html.escape(item.product_name)}</div>
                {variant_line}
                <div style="font-size: 12px; color: #64748b; margin-top: 3px;">Qty: {int(item.quantity or 1)} × {_format_currency(item.price)}</div>
            </td>
            <td style="padding: 12px 0; border-bottom: 1px solid #f1f5f9; text-align: right; font-size: 14px; font-weight: 700; color: #0f172a; vertical-align: top;">
                {line_total}
            </td>
        </tr>""")

    shipping_label = "FREE" if float(order.shipping_cost or 0) == 0 else _format_currency(order.shipping_cost)
    customer_name = html.escape(order.customer_name or "Valued Customer")
    shipping_address = html.escape(order.shipping_address or "")
    customer_phone = html.escape(order.customer_phone or "")
    payment_method = html.escape(order.payment_method or "Cash on Delivery")

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Order Confirmed #{order.id} - Eacyclic</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px 12px; color: #1e293b;">
    <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;">
        <div style="background: linear-gradient(135deg, #134e35 0%, #0e3a27 100%); padding: 32px 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 26px; font-weight: 900; letter-spacing: -0.5px;">Eacyclic</div>
            <div style="display: inline-block; margin-top: 10px; background: rgba(255,255,255,0.14); padding: 5px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;">
                ✓ Order Confirmed
            </div>
        </div>

        <div style="padding: 30px 26px;">
            <h1 style="margin: 0 0 8px 0; font-size: 21px; font-weight: 800; color: #0f172a;">
                Thank you for your order, {customer_name}!
            </h1>
            <p style="margin: 0 0 22px 0; font-size: 14px; color: #475569; line-height: 1.6;">
                We've received your order and are preparing it for dispatch. You can track your delivery live anytime using the button below.
            </p>

            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 14px; padding: 16px; margin-bottom: 24px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr>
                        <td style="padding: 3px 0; color: #475569;">Order ID</td>
                        <td style="padding: 3px 0; text-align: right; font-weight: 800; color: #0f172a;">#{order.id}</td>
                    </tr>
                    <tr>
                        <td style="padding: 3px 0; color: #475569;">Tracking Number</td>
                        <td style="padding: 3px 0; text-align: right; font-weight: 700; color: #134e35;">{html.escape(tracking_number)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 3px 0; color: #475569;">Estimated Delivery</td>
                        <td style="padding: 3px 0; text-align: right; font-weight: 700; color: #0f172a;">{est_date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 3px 0; color: #475569;">Payment Method</td>
                        <td style="padding: 3px 0; text-align: right; font-weight: 700; color: #0f172a;">{payment_method}</td>
                    </tr>
                </table>
            </div>

            <div style="font-size: 12px; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px;">
                Items Ordered
            </div>
            <table style="width: 100%; border-collapse: collapse;">
                {''.join(items_html)}
            </table>

            <table style="width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px;">
                <tr>
                    <td style="padding: 4px 0; color: #64748b;">Subtotal</td>
                    <td style="padding: 4px 0; text-align: right; font-weight: 600; color: #0f172a;">{_format_currency(order.subtotal)}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #64748b;">Delivery</td>
                    <td style="padding: 4px 0; text-align: right; font-weight: 700; color: #134e35;">{shipping_label}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0 0 0; border-top: 1px solid #e2e8f0; font-size: 16px; font-weight: 800; color: #0f172a;">Order Total</td>
                    <td style="padding: 10px 0 0 0; border-top: 1px solid #e2e8f0; text-align: right; font-size: 18px; font-weight: 900; color: #134e35;">{_format_currency(order.total)}</td>
                </tr>
            </table>

            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; margin-top: 22px;">
                <div style="font-size: 12px; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;">
                    Delivery Address
                </div>
                <div style="font-size: 13px; font-weight: 700; color: #0f172a;">{customer_name}</div>
                <div style="font-size: 13px; color: #475569; line-height: 1.5; margin-top: 3px;">{shipping_address}</div>
                <div style="font-size: 13px; color: #475569; margin-top: 4px;">Phone: {customer_phone}</div>
            </div>

            <div style="text-align: center; margin-top: 28px;">
                <a href="{track_url}" style="display: inline-block; background: #134e35; color: #ffffff; text-decoration: none; font-weight: 700; font-size: 14px; padding: 13px 28px; border-radius: 999px; margin: 4px;">
                    Track Your Order
                </a>
                <a href="{shop_url}" style="display: inline-block; background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; text-decoration: none; font-weight: 700; font-size: 14px; padding: 12px 24px; border-radius: 999px; margin: 4px;">
                    Shop More Deals
                </a>
            </div>
        </div>

        <div style="background-color: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #f1f5f9; line-height: 1.6;">
            Need help? Reply or message us on WhatsApp at <strong>+91 98460 07257</strong> or email <strong>eacyclic@gmail.com</strong>.<br/>
            &copy; {timezone.now().year} Eacyclic. All rights reserved.
        </div>
    </div>
</body>
</html>"""


def dispatch_order_confirmation_email_async(order):
    """Send customer receipt email and admin order alert email asynchronously."""
    site_url = getattr(settings, 'SITE_URL', 'https://eacyclic.com')
    customer_email = (order.customer_email or '').strip()
    item_lines = [
        f"- {item.product_name} (Qty: {item.quantity}) - {_format_currency(float(item.price or 0) * int(item.quantity or 1))}"
        for item in order.items.all()
    ]
    items_text = "\n".join(item_lines)

    if customer_email:
        subject = f"Order Confirmed #{order.id} - Eacyclic"
        plain_message = (
            f"Hi {order.customer_name},\n\n"
            f"Thank you for shopping with Eacyclic! Your order #{order.id} has been confirmed.\n\n"
            f"Items:\n{items_text}\n\n"
            f"Total: {_format_currency(order.total)} ({order.payment_method})\n"
            f"Delivery Address: {order.shipping_address}\n\n"
            f"Track your order here: {site_url}/order-status/{order.id}\n\n"
            "Need help? Contact us at +91 98460 07257 or eacyclic@gmail.com."
        )
        html_message = generate_order_confirmation_html_email(order)
        dispatch_email_async([customer_email], subject, plain_message, html_message, tag="ORDER CONFIRM EMAIL")

    admin_email = getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', '').strip()
    if admin_email and admin_email.lower() != customer_email.lower():
        admin_subject = f"New Order #{order.id} ({_format_currency(order.total)}) - {order.customer_name}"
        admin_plain = (
            f"New order received on Eacyclic!\n\n"
            f"Order ID: #{order.id}\n"
            f"Customer: {order.customer_name}\n"
            f"Phone: {order.customer_phone}\n"
            f"Email: {customer_email or 'Not provided'}\n"
            f"Total: {_format_currency(order.total)} ({order.payment_method})\n"
            f"Address: {order.shipping_address}\n\n"
            f"Items:\n{items_text}\n\n"
            f"Manage orders: {site_url}/admin/orders/{order.id}"
        )
        admin_html = generate_order_confirmation_html_email(order)
        dispatch_email_async([admin_email], admin_subject, admin_plain, admin_html, tag="ADMIN ORDER ALERT")


def dispatch_order_status_email_async(order, new_status):
    """Notify customer when order status changes (processing, shipped, delivered, cancelled)."""
    customer_email = (order.customer_email or '').strip()
    if not customer_email:
        return

    status_key = (new_status or '').strip().lower()
    status_copy = {
        'processing': ('Your Order is Being Packed', 'Our team is carefully inspecting and packing your items for dispatch.'),
        'shipped': ('Your Order Has Shipped!', 'Great news! Your package is on the way to your doorstep.'),
        'out_for_delivery': ('Out for Delivery Today', 'Your courier partner is nearby and will deliver your package today.'),
        'delivered': ('Order Delivered — Enjoy Your Purchase!', 'Your order has been delivered. Thank you for choosing Eacyclic — we hope to see you again soon!'),
        'cancelled': ('Order Cancelled', 'Your order has been cancelled as requested. If you need anything else, we are always here to help.'),
    }
    headline, detail = status_copy.get(
        status_key,
        (f"Order Status Updated: {new_status.title()}", f"Your order #{order.id} status is now {new_status}.")
    )
    site_url = getattr(settings, 'SITE_URL', 'https://eacyclic.com')
    track_url = f"{site_url}/order-status/{order.id}"
    shop_url = f"{site_url}/product"
    delivery = getattr(order, 'delivery', None)
    tracking_line = (
        f"<p style='font-size:13px; color:#134e35; font-weight:700;'>Tracking ID: {html.escape(delivery.tracking_number)}</p>"
        if delivery and delivery.tracking_number
        else ""
    )

    subject = f"{headline} (#{order.id}) - Eacyclic"
    plain_message = (
        f"Hi {order.customer_name},\n\n{headline}\n{detail}\n\n"
        f"Order ID: #{order.id}\n"
        f"Track status: {track_url}\n"
        f"Shop again: {shop_url}\n"
    )
    html_message = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background:#f8fafc; padding:24px 12px; color:#1e293b;">
    <div style="max-width:520px; margin:0 auto; background:#fff; border-radius:18px; border:1px solid #e2e8f0; overflow:hidden;">
        <div style="background:#134e35; padding:24px; text-align:center; color:#fff;">
            <div style="font-size:24px; font-weight:900;">Eacyclic</div>
            <div style="font-size:12px; opacity:0.9; margin-top:4px;">Order #{order.id} Update</div>
        </div>
        <div style="padding:28px 24px;">
            <h2 style="margin:0 0 8px 0; font-size:19px; color:#0f172a;">{html.escape(headline)}</h2>
            <p style="font-size:14px; color:#475569; line-height:1.6;">Hi {html.escape(order.customer_name)}, {html.escape(detail)}</p>
            {tracking_line}
            <div style="margin-top:24px; text-align:center;">
                <a href="{track_url}" style="display:inline-block; background:#134e35; color:#fff; text-decoration:none; font-weight:700; font-size:13px; padding:12px 24px; border-radius:999px; margin:4px;">Track Order</a>
                <a href="{shop_url}" style="display:inline-block; background:#fff7ed; color:#c2410c; border:1px solid #fed7aa; text-decoration:none; font-weight:700; font-size:13px; padding:11px 22px; border-radius:999px; margin:4px;">Order Again</a>
            </div>
        </div>
    </div>
</body>
</html>"""
    dispatch_email_async([customer_email], subject, plain_message, html_message, tag="ORDER STATUS EMAIL")


def dispatch_contact_notification_async(contact):
    """Alert store admin when a contact form message is submitted."""
    admin_email = getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', '').strip()
    if not admin_email:
        return
    subject = f"New Store Inquiry: {contact.subject} ({contact.name})"
    plain_message = (
        f"New contact inquiry on Eacyclic:\n\n"
        f"Name: {contact.name}\n"
        f"Email: {contact.email}\n"
        f"Phone: {contact.phone}\n"
        f"Subject: {contact.subject}\n\n"
        f"Message:\n{contact.message}\n"
    )
    html_message = f"""<html><body style="font-family:Arial,sans-serif;color:#1e293b;">
    <h3>New Store Inquiry on Eacyclic</h3>
    <p><strong>Name:</strong> {html.escape(contact.name)}</p>
    <p><strong>Email:</strong> {html.escape(contact.email)}</p>
    <p><strong>Phone:</strong> {html.escape(contact.phone)}</p>
    <p><strong>Subject:</strong> {html.escape(contact.subject)}</p>
    <p><strong>Message:</strong><br/>{html.escape(contact.message)}</p>
    </body></html>"""
    dispatch_email_async([admin_email], subject, plain_message, html_message, tag="CONTACT ALERT")
