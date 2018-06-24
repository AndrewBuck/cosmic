from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Sum
from paypal.standard.models import ST_PP_COMPLETED
from paypal.standard.ipn.signals import valid_ipn_received

from .models import *

def handlePaypalRecieved(sender, **kwargs):
    print('Handling IPN payment response.')
    ipn_obj = sender
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # WARNING !
        # Check that the receiver email is the same we previously
        # set on the `business` field. (The user could tamper with
        # that fields on the payment form before it goes to PayPal)
        if ipn_obj.receiver_email != settings.PAYPAL_RECEIVER_EMAIL:
            # Not a valid payment
            return

        # ALSO: for the same reason, you need to check the amount
        # received, `custom` etc. are all what you expect or what
        # is allowed.

        user = User.objects.filter(pk=ipn_obj.item_number).first()

        # Undertake some action depending upon `ipn_obj`.
        if ipn_obj.custom == "premium_plan":
            print('Premium plan donation recieved of {} {} from user id {}'\
                .format(ipn_obj.mc_gross, ipn_obj.mc_currency, ipn_obj.item_number))

            #TODO: Handle currency conversions somehow.
            with transaction.atomic():
                siteDonation = SiteDonation(
                    user = user,
                    text = ipn_obj.item_name,
                    amount = ipn_obj.mc_gross
                    )

                siteDonation.save()

                siteCost = SiteCost(
                    user = user,
                    dateTime = ipn_obj.created_at,
                    text = 'Paypal Donation Fee',
                    cost = ipn_obj.mc_fee
                    )

                siteCost.save()
                totalDonations = SiteDonation.objects\
                    .filter(user=user)\
                    .aggregate(Sum('amount'))['amount__sum']

                user.profile.totalDonations = totalDonations
                user.profile.save()

print('Registering IPN payment hook.')
valid_ipn_received.connect(handlePaypalRecieved)
