resource "aws_key_pair" "public_key" {
  key_name   = "public_key"
  public_key = file("public.key")
}
