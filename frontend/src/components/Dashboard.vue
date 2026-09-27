<template>
  <div style="max-width: 600px; margin: 40px auto; padding: 20px; border: 1px solid #ccc; border-radius: 8px;">
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 20px;">
      <h2>📦 Inventory Dashboard</h2>
      <button @click="$emit('logout')" style="padding: 5px 10px; background-color: #f44336; color: white; border: none; cursor: pointer;">Logout</button>
    </div>

    <div style="background-color: #f9f9f9; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
      <h3>Add New Product</h3>
      <form @submit.prevent="addProduct" style="display: flex; gap: 10px;">
        <input v-model="newProduct.name" placeholder="Product Name" required style="flex: 2; padding: 8px;" />
        <input v-model.number="newProduct.quantity" type="number" min="0" placeholder="Qty" required style="flex: 1; padding: 8px;" />
        <button type="submit" style="padding: 8px 15px; background-color: #008CBA; color: white; border: none; cursor: pointer;">Add</button>
      </form>
    </div>

    <p v-if="errorMessage" style="color: #f44336;">{{ errorMessage }}</p>

    <h3>Current Inventory</h3>
    <ul style="list-style-type: none; padding: 0;">
      <li v-for="product in products" :key="product.id" style="padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; gap: 10px;">
        <strong style="flex: 1; text-align: left;">{{ product.name }}</strong>
        <span style="display: flex; align-items: center; gap: 6px;">
          <button @click="changeQuantity(product, -1)" :disabled="product.quantity === 0" style="width: 28px; cursor: pointer;">−</button>
          <span style="min-width: 90px; text-align: center;">Quantity: {{ product.quantity }}</span>
          <button @click="changeQuantity(product, 1)" style="width: 28px; cursor: pointer;">+</button>
          <button @click="deleteProduct(product)" style="margin-left: 8px; padding: 4px 8px; background-color: #f44336; color: white; border: none; cursor: pointer;">Delete</button>
        </span>
      </li>
    </ul>
    <p v-if="products.length === 0" style="color: #777;">No products in inventory yet.</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api';

defineEmits(['logout']);

const products = ref([]);
const newProduct = ref({ name: '', quantity: '' });
const errorMessage = ref('');

// The token is added automatically by the interceptor in api.js
const run = async (action, failMsg) => {
  errorMessage.value = '';
  try {
    await action();
  } catch (error) {
    if (error.response?.status !== 401) errorMessage.value = failMsg;
    console.error(failMsg, error);
  }
};

const fetchInventory = () => run(async () => {
  const response = await api.get('/inventory/products');
  products.value = response.data;
}, 'Could not load inventory.');

const addProduct = () => run(async () => {
  await api.post('/inventory/products', newProduct.value);
  newProduct.value = { name: '', quantity: '' };
  await fetchInventory();
}, 'Could not add product.');

const changeQuantity = (product, delta) => run(async () => {
  const quantity = Math.max(0, product.quantity + delta);
  await api.put(`/inventory/products/${product.id}`, { quantity });
  product.quantity = quantity;
}, 'Could not update quantity.');

const deleteProduct = (product) => run(async () => {
  await api.delete(`/inventory/products/${product.id}`);
  products.value = products.value.filter((p) => p.id !== product.id);
}, 'Could not delete product.');

onMounted(fetchInventory);
</script>
