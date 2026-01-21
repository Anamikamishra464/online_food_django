from django.shortcuts import render,redirect
from marketplace.models import Cart,Tax
from marketplace.context_processor import get_cart_amounts
from . forms import OrderForm
from .models import Order
import simplejson as json
from .utils import generate_order_number
from django.http import HttpResponse,JsonResponse 
from .models import Payment,OrderedFood
from menu.models import FoodItem
from vendor.models import Vendor
import stripe
from django.conf import settings
from marketplace.models import Cart


stripe.api_key=settings.STRIPE_API_KEY

# Create your views here.
def place_order(request):
    cart_items=Cart.objects.filter(user=request.user).order_by('created_at')
    cart_count=cart_items.count()
    if cart_count<=0:
        return redirect('marketplace')
    vendors_ids=[]
    for i in cart_items:
        if i.fooditem.vendor.id not in vendors_ids:
            vendors_ids.append(i.fooditem.vendor.id)  # keep this, it's correct
            
            
    get_tax=Tax.objects.filter(is_active=True)
    subtotal=0
    k={}
    total_data={}
    for i in cart_items:
        vendors = Vendor.objects.filter(id__in=vendors_ids)
        fooditem = FoodItem.objects.get(pk=i.fooditem.id, vendor__in=vendors)
        v_id=fooditem.vendor.id
        if v_id in k:
            subtotal=k[v_id]
            subtotal +=(fooditem.price * i.quantity)
            k[v_id]=subtotal
        else:
            subtotal=(fooditem.price * i.quantity)
            k[v_id]=subtotal
            
    # calculate tax data
            tax_dict={}
            for i in get_tax:
                tax_type=i.tax_type
                tax_percentage=i.tax_percentage
                tax_amount=round((tax_percentage* subtotal)/100,2)
                tax_dict.update({tax_type:{str(tax_percentage):str(tax_amount)}})
        #construct total data
                total_data.update({fooditem.vendor.id:{str(subtotal):str(tax_dict)}})     
            
    subtotal =get_cart_amounts(request)['subtotal']
    total_tax =get_cart_amounts(request)['tax']
    grand_total =get_cart_amounts(request)['grand_total']
    tax_data =get_cart_amounts(request)['tax_dict']
    
    if request.method== 'POST':
        form=OrderForm(request.POST)
        if form.is_valid():
            order=Order()
            order.first_name= form.cleaned_data['first_name']
            order.last_name= form.cleaned_data['last_name']
            order.phone= form.cleaned_data['phone']
            order.email= form.cleaned_data['email']
            order.address= form.cleaned_data['address']
            order.country= form.cleaned_data['country']
            order.state= form.cleaned_data['state']
            order.city= form.cleaned_data['city']
            order.pin_code= form.cleaned_data['pin_code']
            order.user=request.user
            order.total=grand_total
            order.tax_data= json.dumps(tax_data)
            order.total_data=json.dumps(total_data)
            order.total_tax=total_tax
            order.payment_method= request.POST['payment_method']
            order.save() #order if/ pk generated
            order.order_number=generate_order_number(order.id)
            order.vendor.add(*vendors_ids)
            order.save() 
            context={
                'order':order,
                'cart_items':cart_items,
                'user': request.user,

            }

            return render(request,'orders/place_order.html',context)
        else:
            print(form.errors)
    return render(request,'orders/place_order.html')

def payments (request):
    # Check if the request is ajax or not
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        #STORE THE PAYMENT DETAILS IN THE PAYMENT MODEL
        order_number = request.POST.get('order_number')
        transaction_id = request.POST.get('transaction_id')
        payment_method = request.POST.get('payment_method')
        status = request.POST.get('status')
        order = Order.objects.get(user=request.user, order_number=order_number)
        payment = Payment(
            user = request.user,
            transaction_id = transaction_id,
            payment_method=payment_method,
            amount = order.total,
            status = status,
        )
        payment.save()
        # UPDATE THE ORDER MODEL
        order.payment=payment
        order.is_ordered=True
        order.save()
      
        # MOVE THE CART ITEMS TO ORDERED FOOD MODEL
        cart_items=Cart.objects.filter(user=request.user)
        for item in cart_items:
            ordered_food=OrderedFood()
            ordered_food.order=order
            ordered_food.payment= payment
            ordered_food.user=request.user
            ordered_food.fooditem= item.fooditem
            ordered_food.quantity= item.quantity
            ordered_food.price= item.fooditem.price
            ordered_food.amount= item.fooditem.price * item.quantity #total amount
            ordered_food.save()
            response={
                'order_number':order_number,
                'transaction_id':transaction_id,
            }
        return JsonResponse (response)
                
    return HttpResponse('Payment view')

def order_complete(request):
    order_number=request.GET.get('order_no')
    transaction_id=request.GET.get('trans_id')

    try:
        order= Order.objects.get(order_number=order_number,payment__transaction_id=transaction_id,is_ordered=True)
        ordered_food=OrderedFood.objects.filter(order=order)
        subtotal=0
        for item in ordered_food:
            subtotal += (item.price * item.quantity)
            tax_data = json.loads(order.tax_data)
            print(tax_data)
        context={
            'order':order,
            'ordered_food':ordered_food,
            'subtotal': subtotal,
            'tax_data':tax_data
        }
        print(order,ordered_food)
        return render(request,'orders/order_complete.html',context)

    except:
        return redirect('home')

def create_checkout_session(request):
    if not request.user.is_authenticated:
        return redirect('login')

    cart_items = Cart.objects.filter(user=request.user)
    if not cart_items.exists():
        return redirect('cart')

    # get existing tax + totals
    cart_amounts = get_cart_amounts(request)
    grand_total = cart_amounts['grand_total']

    # Get latest un-ordered order
    order = Order.objects.filter(user=request.user, is_ordered=False).last()

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[
            {
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Food Order Payment',
                    },
                    'unit_amount': int(grand_total * 100),
                },
                'quantity': 1,
            }
        ],
        mode='payment',

        # Store order_number for redirect after payment
        metadata={
            "order_number": order.order_number
        },

        success_url=request.build_absolute_uri('/payments/'),
        cancel_url=request.build_absolute_uri('/payment-cancel/'),
        customer_email=request.user.email if request.user.email else None,
    )

    return redirect(checkout_session.url)





def payment_success(request):
    # Optional: Move cart items to Order model
    Cart.objects.filter(user=request.user).delete()
    return render(request, 'payment_success.html')

def payment_cancel(request):
    return render(request, 'payment_cancel.html')
