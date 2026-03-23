from unstructured.partition.pdf import partition_pdf

elements = partition_pdf('罗森瀚-硕士-南京邮电大学.pdf.pdf')

for el in elements:

    print(str(el))