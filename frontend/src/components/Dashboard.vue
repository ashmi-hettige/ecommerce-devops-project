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
        <input v-model.number="newProduct.quantity" type="number" placeholder="Qty" required style="flex: 1; padding: 8px;" />
        <button type="submit" style="padding: 8px 15px; background-color: #008CBA; color: white; border: none; cursor: pointer;">Add</button>
      </form>
    </div>

    <h3>Current Inventory</h3>
    <ul style="list-style-type: none; padding: 0;">
      <li v-for="(product, index) in products" :key="index" style="padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between;">
        <strong>{{ product.name }}</strong>
        <span>Quantity: {{ product.quantity }}</span>
      </li>
    </ul>
    <p v-if="products.length === 0" style="color: #777;">No products in inventory yet.</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import axios from 'axios';

const props = defineProps(['token']);
const emit = defineEmits(['logout']);

const products = ref([]);
const newProduct = ref({ name: '', quantity: '' });
const API_URL = 'http://127.0.0.1:8000';

const fetchInventory = async () => {
  try {
    const response = await axios.get(`${API_URL}/inventory`);
    products.value = response.data;
  } catch (error) {
    console.error("Error fetching inventory", error);
  }
};

const addProduct = async () => {
  try {
    await axios.post(`${API_URL}/inventory`, newProduct.value);
    newProduct.value = { name: '', quantity: '' };
    fetchInventory(); // Refresh the list
  } catch (error) {
    console.error("Error adding product", error);
  }
};

// Automatically fetch data when the dashboard loads
onMounted(() => {
  fetchInventory();
});
</script>