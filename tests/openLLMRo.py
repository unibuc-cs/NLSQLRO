from transformers import AutoTokenizer, AutoModelForCausalLM

tokenizer = AutoTokenizer.from_pretrained("OpenLLM-Ro/RoLlama3-8b-Instruct")
model = AutoModelForCausalLM.from_pretrained("OpenLLM-Ro/RoLlama3-8b-Instruct")

instruction = "Ce jocuri de societate pot juca cu prietenii mei?"
chat = [
        {"role": "system", "content": "Ești un asistent folositor, respectuos și onest. Încearcă să ajuți cât mai mult prin informațiile oferite, excluzând răspunsuri toxice, rasiste, sexiste, periculoase și ilegale."},
        {"role": "user", "content": instruction},
        ]
prompt = tokenizer.apply_chat_template(chat, tokenize=False, system_message="")

inputs = tokenizer.encode(prompt, add_special_tokens=False, return_tensors="pt")
outputs = model.generate(input_ids=inputs, max_new_tokens=128)
print(tokenizer.decode(outputs[0]))