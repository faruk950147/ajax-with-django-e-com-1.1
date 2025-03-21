from ast import Try
from turtle import color
from django.shortcuts import render,redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.views import generic
from django.utils import timezone
from django.http import HttpResponseRedirect, JsonResponse, HttpResponseBadRequest
from django.db.models import Min, Max
import json
from stories.models import (
    Category,Brand,Product, Images,Color,Size,Variants,Slider,Banner,Future,Review
)
from cart.forms import CartForm
#import store models

# Create your views here.
# Home View
@method_decorator(never_cache, name='dispatch')
class HomeView(generic.View):
    def get(self, request):
        context = {
            'sliders': Slider.objects.filter(status=True).order_by('id'),
            'banners': Banner.objects.filter(status=True).order_by('id')[:3],
            'side_deals_banners': Banner.objects.filter(status=True, side_deals=True, side_deals_is_active=True).order_by('id')[:1],
            'deals_products': Product.objects.filter(offers_deadline__isnull=False,  is_timeline=True, deals=True, status=True).order_by("id")[:6],
            'current_time': timezone.now(),
            'new_collections': Product.objects.filter(status=True, new_collection=True).order_by('id')[:4], 
            'girls_collections': Product.objects.filter(status=True, girls_collection=True).order_by('id')[:4],
            'men_collections': Product.objects.filter(status=True, men_collection=True).order_by('id')[:4],
            'latest_collections': Product.objects.filter(status=True, latest_collection=True).order_by('id')[:4],
            'pick_collections': Product.objects.filter(status=True, pick_collection=True).order_by('id')[:4],  
        }
        return render(request, 'stories/home.html', context)
    
# Single Product View
def SingleProductView(request, id):
    product = get_object_or_404(Product, id=id)
    related_products = Product.objects.filter(category=product.category).exclude(id=id).select_related('category').order_by('-id')[:4]
    reviews = Review.objects.filter(product=product, status=True).select_related('user')
    reviews_total = reviews.count()

    context = {
        'product': product,
        'related_products': related_products,
        'reviews': reviews,
        'reviews_total': reviews_total,
        'variant': None,  # Default variant
    }

    if product.variant != "None":
        variants = Variants.objects.filter(product_id=id)
        variant = None

        if request.method == 'POST' and 'colorid' in request.POST:
            color_id = request.POST.get('colorid')
            variant = Variants.objects.filter(id=color_id).first()

        # Handle 'Colors' variant specifically
        if product.variant == 'Colors':
            colors = variants  # Use the same 'variants' query for colors
            context['colors'] = colors  # Add colors directly to context
        elif product.variant == 'Sizes' or product.variant == 'Sizes-Colors':
            # Fetch sizes for 'Sizes' or 'Sizes-Colors' variant
            sizes = Variants.objects.raw('SELECT * FROM stories_variants WHERE product_id=%s GROUP BY size_id', [id]) if variants.exists() else []
            context['sizes'] = sizes  # Add sizes directly to context

        context['variant'] = variant

    return render(request, 'stories/single.html', context)

# AJAX VIEWS
def ajax_variant_select_sizes(request):
    """ Updates the color options when Size is changed """
    if request.method == 'POST':
        productid = request.POST.get('productid')
        size_id = request.POST.get('size')
        
        if not productid:
            return JsonResponse({'status': 400, 'messages': 'Invalid product ID'})

        # All variants of the product are queried only once
        variants = Variants.objects.filter(product_id=productid)

        if size_id:
            """If only Size is selected, filter colors based on the selected Size."""
            colors = variants.filter(size_id=size_id).distinct()  # Filter colors based on the selected Size
            
            # Get first matching variant (optimized)
            selected_variant = variants.filter(size_id=size_id).first()

            selected_size_title = selected_variant.size.title if selected_variant else "Unknown Size"
            selected_price = selected_variant.price if selected_variant else None

            return JsonResponse({
                'status': 200,
                'messages': 'Size selected successfully',
                'rendered_table': render_to_string('color_list.html', {'colors': colors}),
                'size': selected_size_title,
                'price': selected_price
            })

    return JsonResponse({'messages': 'Invalid request'})

def ajax_variant_select_color(request):
    """ Updates variant details when a color is selected """
    if request.method == 'POST':
        productid = request.POST.get('productid')
        color_id = request.POST.get('color')

        if not productid:
            return JsonResponse({'status': 400, 'messages': 'Invalid product ID'})

        variants = Variants.objects.filter(product_id=productid)
        
        if color_id:
            selected_variant = variants.filter(color_id=color_id).first()

            if selected_variant:
                selected_color_title = selected_variant.color.title if selected_variant.color else "No title available"
                selected_price = selected_variant.price if selected_variant.price else "No price available"
                return JsonResponse({
                    'status': 200,
                    'messages': 'Color variant found for the selected color',
                    'color': selected_color_title,
                    'price': selected_price  
                })
            else:
                return JsonResponse({'status': 400, 'messages': 'No variant found for the selected color'})

    return JsonResponse({'status': 400, 'messages': 'Invalid request method'})

# Reviews View  
@method_decorator(never_cache, name='dispatch')
class ReviewsView(LoginRequiredMixin, generic.View):
    login_url = reverse_lazy('sign')
    def post(self, request):  
        if request.method == "POST":
            try:
                data = json.loads(request.body)
                # Check if updating an existing review
                review_id = data.get("review_id")  
                # Get product ID from request
                product_id = data.get("product_id")  
                # Get the form data
                subject = data.get("subject")
                comment = data.get("comment")
                rate = int(data.get("rate"))
                    
                product = get_object_or_404(Product, id=product_id)  # Ensure product exists
                    
                # Rating validation (1 to 5)
                if not (1 <= rate <= 5):
                    return JsonResponse({"status": 400, "messages": "Invalid rating. Must be between 1 and 5."})

                # Check if the user has already reviewed this product
                if not review_id:
                    existing_review = Review.objects.filter(product=product, user=request.user).first()
                    if existing_review:
                            return JsonResponse({"status": 400, "messages": "You have already reviewed this product."})
                
                if review_id:  # Editing an existing review
                    review = get_object_or_404(Review, id=review_id, user_id=request.user.id)
                    review.subject = subject
                    review.comment = comment
                    review.rate = rate
                    review.save()
                else:  # Creating a new review
                    review = Review()
                    review.product = product
                    review.user_id = request.user.id
                    review.subject = subject
                    review.comment = comment
                    review.rate = rate
                    review.save()
                return JsonResponse({
                    "status": 200,
                    "review_id": review.id,
                    "product_id": review.product.id,
                    "user": review.user.username,
                    "subject": review.subject,
                    "comment": review.comment,
                    "rate": review.rate,  
                    "updated_date": review.updated_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "messages": "Review added successfully"
                })
            except Review.DoesNotExist:
                return JsonResponse({"status": 400, "messages": "Review not found for this user"})
            except Exception as e:
                return JsonResponse({"status": 400, "messages": str(e)})