from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Category, Brand, Product, Cart, CartItem, Order, OrderItem
from .forms import CartAddProductForm, OrderCreateForm
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, CustomAuthenticationForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('shop:home')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now log in.')
            return redirect('shop:login')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'shop/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('shop:home')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                
                # Redirect to next URL if provided, otherwise to home
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('shop:home')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'shop/login.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('shop:home')

@login_required
def profile_view(request):
    return render(request, 'shop/profile.html')
    


def product_list(request, category_slug=None):
    category = None
    categories = Category.objects.all()
    products = Product.objects.filter(available=True)
    
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)
    
    # Search functionality
    query = request.GET.get('q')
    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    
    # Filter by brand
    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    # Filter by gender
    gender = request.GET.get('gender')
    if gender:
        products = products.filter(gender=gender)
    
    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)
    
    brands = Brand.objects.all()
    
    return render(request, 'shop/product_list.html', {
        'category': category,
        'categories': categories,
        'products': products,
        'brands': brands,
    })

def product_detail(request, id, slug):
    product = get_object_or_404(Product, id=id, slug=slug, available=True)
    cart_product_form = CartAddProductForm()
    
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'cart_product_form': cart_product_form,
    })

@login_required
def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    form = CartAddProductForm(request.POST)
    
    if form.is_valid():
        cd = form.cleaned_data
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            size=cd['size'],
            defaults={'quantity': cd['quantity']}
        )
        
        if not created:
            if cd['override']:
                cart_item.quantity = cd['quantity']
            else:
                cart_item.quantity += cd['quantity']
            cart_item.save()
        
        messages.success(request, f'{product.name} added to cart successfully!')
    
    return redirect('shop:cart_detail')

@login_required
def cart_remove(request, product_id, size):
    cart = get_object_or_404(Cart, user=request.user)
    product = get_object_or_404(Product, id=product_id)
    
    try:
        cart_item = CartItem.objects.get(cart=cart, product=product, size=size)
        cart_item.delete()
        messages.success(request, 'Item removed from cart!')
    except CartItem.DoesNotExist:
        pass
    
    return redirect('shop:cart_detail')

@login_required
def cart_detail(request):
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.items.all()
    except Cart.DoesNotExist:
        cart = None
        cart_items = []
    
    for item in cart_items:
        item.update_quantity_form = CartAddProductForm(initial={
            'quantity': item.quantity,
            'size': item.size,
            'override': True
        })
    
    return render(request, 'shop/cart.html', {
        'cart': cart,
        'cart_items': cart_items,
    })

@login_required
def order_create(request):
    try:
        cart = Cart.objects.get(user=request.user)
        if not cart.items.exists():
            messages.error(request, 'Your cart is empty!')
            return redirect('shop:cart_detail')
    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty!')
        return redirect('shop:cart_detail')
    
    if request.method == 'POST':
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user
            order.total_cost = cart.get_total_price()
            order.save()
            
            for item in cart.items.all():
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    size=item.size,
                    price=item.product.get_price(),
                    quantity=item.quantity
                )
            
            cart.delete()
            messages.success(request, f'Your order #{order.id} has been placed successfully!')
            return redirect('shop:product_list')
    else:
        form = OrderCreateForm()
    
    return render(request, 'shop/order_create.html', {
        'cart': cart,
        'form': form,
    })

@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).order_by('-created')
    
    return render(request, 'shop/order_list.html', {
        'orders': orders,
    })

@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status in ["pending", "processing"]:
        order.status = "cancelled"
        order.save()
        messages.success(request, f"Order #{order.id} has been cancelled.")
    else:
        messages.error(request, "This order cannot be cancelled.")

    return redirect("shop:order_list")

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    return render(request, 'shop/order_detail.html', {
        'order': order,
    })

def home(request):
    featured_products = Product.objects.filter(available=True)[:8]
    categories = Category.objects.all()[:6]
    brands = Brand.objects.all()[:8]
    
    return render(request, 'shop/home.html', {
        'featured_products': featured_products,
        'categories': categories,
        'brands': brands,
    })

    